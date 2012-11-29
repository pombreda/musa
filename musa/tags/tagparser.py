"""
Tag metadata reader and writer classes
"""

import os,base64

from musa import normalized
from musa.formats import MusaFileFormat 
from musa.tags import TagError
from musa.tags.constants import STANDARD_TAG_ORDER
from musa.tags.albumart import AlbumArt,AlbumArtError

__all__ = ['aac','flac','mp3','vorbis']

class TagParser(dict):
    """
    Parent class for tag parser implementations
    """
    def __init__(self,codec,path,tag_map=None):
        dict.__init__(self)
        self.codec = codec
        self.path = normalized(os.path.realpath(path))
        self.tag_map = tag_map is not None and tag_map or {}
        self.supports_albumart = False
        self.entry = None
        self.modified = False

    def get_unknown_tags(self):
        """
        Must be implemented in child if needed: return empty list here
        """
        return []

    @property
    def get_albumart(self):
        if not self.supports_albumart or not hasattr(self,'albumart'):
            return None
        return self.albumart

    def __getattr__(self,attr):
        try:
            return self[attr]
        except KeyError:
            pass
        raise AttributeError('No such TagParser attribute: %s' % attr)

    def __getitem__(self,item):
        """
        Return tags formatted to unicode, decimal.Decimal or
        other supported types.
        Does not include albumart images, which are accessed
        via self.albumart attribute
        """
        fields = self.__tag2fields__(item)
        for field in fields:
            if field not in self.entry:
                continue
            tag = self.entry[field]
            if not isinstance(tag,list):
                tag = [tag]
            values = []
            for value in tag:
                if not isinstance(value,unicode):
                    if isinstance(value,int):
                        value = unicode('%d'%value)
                    else:
                        try:
                            value = unicode(value,'utf-8')
                        except UnicodeDecodeError,emsg:
                            raise TagError(
                                'Error decoding %s tag %s: %s' % (
                                    self.path,field,emsg
                                )
                            )
                values.append(value)
            return values
        raise KeyError('No such tag: %s' % fields)

    def __setitem__(self,item,value):
        if isinstance(item,AlbumArt):
            try:
                self.albumart.import_albumart(value)
            except AlbumArtError,emsg:
                raise TagError('Error setting albumart: %s' % emsg)
        self.set_tag(item,value)

    def __delitem__(self,item):
        fields = self.__tag2fields__(item)
        for tag in fields:
            if tag not in self.entry.keys():
                continue
            del self.entry[tag]
            self.modified = True

    def __tag2fields__(self,tag):
        """
        Resolve tag name to internal parser field
        """
        for name,tags in self.tag_map.items():
            if tag == name:
                return tags
        return [tag]

    def __field2tag__(self,field):
        """
        Resolve internal parser field to tag name
        """
        for name,tags in self.tag_map.items():
            # Can happen if name is internal reference: ignore here
            if tags is None:
                continue
            if field in tags:
                return name
        return field

    def __flatten_tag__(self,tag):
        try:
            value = self[tag]
        except KeyError:
            return None
        if isinstance(value,basestring):
            return value
        if isinstance(value,list):
            if len(value)==0:
                return None
            if isinstance(value[0],basestring):
                return value[0]
        # Skip non-string tags
        return None

    def __repr__(self):
        return '%s: %s' % (self.codec.description,self.path)

    def get_tag(self,item):
        """
        Return tag from file. Raises TagError if tag is not found
        If tag has multiple values, only first one is returned.
        """
        if not self.has_key(item):
            raise TagError('No such tag: %s' % item) 
        value = self.__flatten_tag__(item)
        if value is None:
            raise TagError('No such string tag: %s' % item) 
        return value

    def set_tag(self,item,value):
        """
        Sets the tag item to given value.
        Must be implemented in child class, this raises
        NotImplementedError
        """
        raise NotImplementedError('Must implement set_tag in child')

    def sort_keys(self,keys):
        """
        Sort keys with STANDARD_TAG_ORDER list
        """
        values = []
        for k in STANDARD_TAG_ORDER:
            if k in keys: values.append(k)
        for k in keys:
            if k not in STANDARD_TAG_ORDER: values.append(k)
        return values

    def has_key(self,key):
        """
        Test if given key is in tags
        """
        keys = self.__tag2fields__(key)
        for k in keys:
            if k in self.entry.keys():
                return True
        return False

    def keys(self):
        """
        Return file tag keys mapped with tag_map.
        """
        return self.sort_keys(
            [self.__field2tag__(k) for k in self.entry.keys()]
        )

    def items(self):
        """
        Return tag,value pairs using tag_map keys.
        If tag has multiple values, only first one is returned.
        """
        tags = []
        for tag in self.keys():
            value = self.__flatten_tag__(tag)
            if value is None:
                continue
            tags.append((tag,value))
        return tags

    def values(self):
        """
        Return tag values from entry.
        If tag has multiple values, only first one is returned.
        """
        values = []
        for tag in self.keys():
            value = self.__flatten_tag__(tag)
            if value is None:
                continue
            values.append(value)
        return values

        return [self[k] for k,v in self.keys()]

    def update_tags(self,data):
        if not isinstance(data,dict):
            raise TagError('Updated tags must be a dictionary instance')
        for k,v in data.items():
            print k,v
            self.set_tag(k,v)
        return self.modified

    def remove_unknown_tags(self):
        """
        Remove any tags which we don't know about.
        """
        for tag in self.unknown_tags:
            del self[tag]
        if self.modified:
            self.save()

    def save(self):
        """
        Save tags to file.
        """
        if not self.modified:
            return
        # TODO - replace with copying of file to new inode
        self.entry.save()

class TrackAlbumart(object):
    """
    Parent class for common albumart operations
    """
    def __init__(self,track):
        self.track  = track
        self.modified = False
        self.albumart = None

    def __repr__(self):
        return self.albumart.__repr__()

    def as_base64_tag(self):
        """
        Return albumart image data as base64_tag tag
        """
        if self.albumart is None:
            raise TagError('Albumart is not loaded')
        return base64_tag(base64.b64encode(self.albumart.dump()))

    def defined(self):
        """
        Returns True if albumart is defined, False otherwise
        """
        if self.albumart is None:
            return False
        return True

    def import_albumart(self,albumart):
        """
        Parent method to set albumart tag. Child class must
        implement actual embedding of the tag to file.
        """
        if not isinstance(albumart,AlbumArt):
            raise TagError('Albumart must be AlbumArt instance')
        if not albumart.is_loaded:
            raise TagError('Albumart to import is not loaded with image.')
        self.albumart = albumart

class TrackNumberingTag(object):
    """
    Parent class for processing track numbering info, including track and
    disk numbers and total counts.

    Fields should be set and read from attributes 'value' and 'total'
    """
    def __init__(self,track,tag):
        self.track = track
        self.tag = tag
        self.f_value = None
        self.f_total = None

    def __repr__(self):
        if self.total is not None:
            return '%d/%d' % (self.value,self.total)
        else:
            return '%d' % (self.value)

    def __getattr__(self,attr):
        if attr == 'value':
            return self.f_value
        if attr == 'total':
            return self.f_total
        raise AttributeError('No such TrackNumberingTag attribute: %s' % attr)

    def __setattr__(self,attr,value):
        if attr in ['value','total']:
            if isinstance(value,list):
                value = value[0]
            try:
                if value is not None:
                    value = int(value)
            except ValueError:
                raise TagError('TrackNumberingTag values must be integers')
            except TypeError:
                raise TagError('TrackNumberingTag values must be integers')
            if attr == 'value':
                self.f_value = value
            if attr == 'total':
                self.f_total = value
        else:
            object.__setattr__(self,attr,value)

    def save_tag(self):
        """
        Export this numbering information back to file tags.

        If value is None, ignore both values without setting tag.
        If total is None but value is set, set total==value.
        """
        raise NotImplementedError('save_tag must be implemented in child class')

class Tags(object):
    """
    Loader for file metadata tags. Tag reading and writing for various
    file formats is implemented by tag formatter classes in module
    soundforest.tags.formats, initialized automatically by this class.
    """
    __instances = {}
    def __init__(self,path,fileformat=None):
        if not Tags.__instances.has_key(path):
            Tags.__instances[path] = Tags.TagParserInstance(path,fileformat)
        self.__dict__['Tags.__instances'] = Tags.__instances
        self.__dict__['path'] = path

    def __getattr__(self,attr):
        return getattr(self.__instances[self.path],attr)

    def __setattr__(self,attr,value):
        return setattr(self.__instances[self.path],attr,value)

    class TagParserInstance(dict):
        def __init__(self,path,fileformat=None):
            dict.__init__(self)
            if not os.path.isfile(path):
                raise TagError('No such file: %s' % path)
            self.path = normalized(os.path.realpath(path))
            if fileformat is None:
                fileformat = MusaFileFormat(path)
            if not isinstance(fileformat,MusaFileFormat):
                raise TagError('File format must be MusaFileFormat instance')
            self.fileformat = fileformat
            if self.fileformat.codec is None:
                raise TagError('Unsupported audio file: %s' % path)
            self.load_tags()

        def load_tags(self):
            if self.fileformat.is_metadata:
                raise TagError('Attempting to load audio tags from metadata file')
            tag_parser = self.fileformat.get_tag_parser()
            if tag_parser is None:
                raise TagError(
                    'No tag parser available for %s' % self.fileformat.path
                )
            self.tags = tag_parser(self.fileformat.codec,self.path)

        @property
        def get_mtime(self):
            return os.stat(self.path).st_mtime

        def get_albumart(self):
            return self.tags.albumart

        def remove_tags(self,tags):
            """
            Remove given list of tags from file 
            """
            for tag in tags:
                if tag not in self.keys():
                    continue
                del self.tags[tag]
            if self.tags.modified:
                self.tags.save()

        def update_tags(self,tags):
            """
            Save tags given in a dictionary to the target file
            """
            if self.tags.update_tags(tags):
                self.tags.save()

        def set_tag(self,tag,value):
            return self.tags.set_tag(tag,value)

        def get_tag(self,tag):
            return self.tags.get_tag(tag)

        def has_key(self,item):
            return self.tags.has_key(item)

        def keys(self):
            return self.tags.keys()

        def items(self):
            return self.tags.items()

        def values (self):
            return self.tags.values()

if __name__ == '__main__':
    import sys
    for f in sys.argv[1:]:
        t = Tags(f)
        #t.remove_tags(['album_artist'])
        #t.update_tags({ 'album_artist': 'Abba', 'android_loop': 'Test', })
        t = Tags(f)
        for k,v in t.items():
            print '%16s %s' % (k,v)
