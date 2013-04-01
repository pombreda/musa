#!/usr/bin/env python
"""Musa Models

SQLAlchemy models for musa configuration and music tree databases

"""

import os
from datetime import datetime,timedelta

from sqlite3 import Connection as SQLite3Connection
from sqlalchemy import create_engine, event, Column, ForeignKey, Integer, Boolean, Date
from sqlalchemy.exc import IntegrityError
from sqlalchemy.types import TypeDecorator, Unicode
from sqlalchemy.orm import sessionmaker, relationship, backref
from sqlalchemy.ext.declarative import declarative_base

from musa import MUSA_USER_DIR, MusaError

DEFAULT_DATABASE = os.path.join(MUSA_USER_DIR, 'musa.sqlite')

Base = declarative_base()


class SafeUnicode(TypeDecorator):

    """SafeUnicode columns

    Safely coerce Python bytestrings to Unicode before passing off to the database.

    """

    impl = Unicode

    def process_bind_param(self, value, dialect):
        if isinstance(value, str):
            value = value.decode('utf-8')
        return value


class Setting(Base):

    """Setting

    Musa internal application preferences

    """

    __tablename__ = 'musa_settings'

    id = Column(Integer, primary_key=True)
    key = Column(SafeUnicode)
    value = Column(SafeUnicode)


class SyncTarget(Base):

    """SyncTarget

    Library tree synchronization target entry

    """

    __tablename__ = 'musa_sync_targets'

    id = Column(Integer, primary_key=True)
    name = Column(SafeUnicode, unique=True)
    type = Column(SafeUnicode)
    src = Column(SafeUnicode)
    dst = Column(SafeUnicode)
    flags = Column(SafeUnicode)
    defaults = Column(Boolean)


class Codec(Base):

    """Codec

    Audio format codecs

    """

    __tablename__ = 'codecs'

    id = Column(Integer, primary_key=True)
    name = Column(SafeUnicode)
    description = Column(SafeUnicode)

    def __repr__(self):
        return self.name


class Extension(Base):

    """Extension

    Filename extensions associated with audio format codecs

    """

    __tablename__ = 'extensions'

    id = Column(Integer, primary_key=True)
    extension = Column(SafeUnicode)
    codec_id = Column(Integer, ForeignKey('codecs.id'), nullable=False)
    codec = relationship('Codec', single_parent=False,
        backref=backref('extensions', order_by=extension, cascade='all, delete, delete-orphan')
    )

    def __repr__(self):
        return self.extension


class Decoder(Base):

    """Decoder

    Audio format codec decoder commands

    """

    __tablename__ = 'decoders'

    id = Column(Integer, primary_key=True)
    priority = Column(Integer)
    command = Column(SafeUnicode)
    codec_id = Column(Integer, ForeignKey('codecs.id'), nullable=False)
    codec = relationship('Codec', single_parent=False,
        backref=backref('decoders', order_by=priority, cascade='all, delete, delete-orphan')
        )

    def __repr__(self):
        return '%s decoder: %s' % (self.codec.name, self.command)


class Encoder(Base):

    """Encoder

    Audio format codec encoder commands

    """

    __tablename__ = 'encoders'

    id = Column(Integer, primary_key=True)
    priority = Column(Integer)
    command = Column(SafeUnicode)
    codec_id = Column(Integer, ForeignKey('codecs.id'), nullable=False)
    codec = relationship('Codec', single_parent=False,
        backref=backref('encoders', order_by=priority, cascade='all, delete, delete-orphan')
    )

    def __repr__(self):
        return '%s encoder: %s' % (self.codec.name, self.command)


class PlaylistSource(Base):

    """PlaylistSource

    Playlist parent folders

    """

    __tablename__ = 'playlist_sources'

    id = Column(Integer, primary_key=True)
    name = Column(SafeUnicode)
    path = Column(SafeUnicode)

    def __repr__(self):
        return '%s: %s' % (self.name, self.path)

    def update(self,session,source):
        for playlist in source:

            directory = os.path.realpath(playlist.directory)
            db_playlist = session.query(Playlist).filter(
                Playlist.parent==self,
                Playlist.folder==directory,
                Playlist.name==playlist.name,
                Playlist.extension==playlist.extension
            ).first()

            if db_playlist is None:
                db_playlist = Playlist(
                    parent=self,
                    folder=directory,
                    name=playlist.name,
                    extension=playlist.extension
                )
                session.add(db_playlist)

            for existing_track in db_playlist.tracks:
                session.delete(existing_track)

            playlist.read()
            tracks = []
            for index,path in enumerate(playlist):
                position = index+1
                tracks.append(PlaylistTrack(playlist=db_playlist,path=path,position=position))
            session.add_all(tracks)
            db_playlist.updated = datetime.now()
            session.commit()


class Playlist(Base):

    """Playlist

    Playlist file of audio tracks

    """

    __tablename__ = 'playlists'

    id = Column(Integer, primary_key=True)

    updated = Column(Date)
    folder = Column(SafeUnicode)
    name = Column(SafeUnicode)
    extension = Column(SafeUnicode)
    description = Column(SafeUnicode)

    parent_id = Column(Integer, ForeignKey('playlist_sources.id'), nullable=False)
    parent = relationship('PlaylistSource', single_parent=False,
        backref=backref('playlists', order_by=[folder, name], cascade='all, delete, delete-orphan')
    )

    def __repr__(self):
        return '%s: %d tracks' % (os.sep.join([self.folder, self.name]), len(self.tracks))

    def __len__(self):
        return len(self.tracks)

class PlaylistTrack(Base):

    """PlaylistTrack

    Audio track in a playlist

    """

    __tablename__ = 'playlist_tracks'

    id = Column(Integer, primary_key=True)

    position = Column(Integer)
    path = Column(SafeUnicode)

    playlist_id = Column(Integer, ForeignKey('playlists.id'), nullable=False)
    playlist = relationship('Playlist', single_parent=False,
        backref=backref('tracks', order_by=position, cascade='all, delete, delete-orphan')
    )

    def __repr__(self):
        return '%d %s' % (self.position, self.path)


class TreeType(Base):

    """TreeType

    Audio file tree types (music, samples, loops etc.)

    """

    __tablename__ = 'treetypes'

    id = Column(Integer, primary_key=True)
    name = Column(SafeUnicode)
    description = Column(SafeUnicode)

    def __repr__(self):
        return self.name


class Tree(Base):

    """Tree

    Audio file tree

    """

    __tablename__ = 'trees'

    id = Column(Integer, primary_key=True)
    path = Column(SafeUnicode,unique=True)
    description = Column(SafeUnicode)

    type_id = Column(Integer, ForeignKey('treetypes.id'), nullable=True)
    type = relationship('TreeType', single_parent=True,
        backref=backref('trees', order_by=path, cascade='all, delete, delete-orphan')
    )

    def __repr__(self):
        return self.path

    def update(self,session,tree):
        added,updated,deleted = 0,0,0

        existing_paths = [track.path for track in self.tracks]
        for track in tree:
            if track.path not in existing_paths:
                db_track = Track(
                    tree=self,
                    directory=track.directory,
                    filename=track.filename,
                    extension=track.extension,
                    mtime=track.mtime,
                    deleted=False,
                )
                db_track.update_tags(session,track.tags)
                added +=1

            else:
                db_track = session.query(Track).filter(Track.directory == track.path.directory,Track.filename == track.path.filename).first()
                if db_track:
                    if track.mtime != db_track.mtime:
                        db_track.update_tags(session,track.tags)
                        updated += 1

            session.commit()

        for track in self.tracks:
            if not track.exists:
                session.delete(track)
                deleted += 1

            session.commit()

        return added,updated,deleted

    def match(self,match):
        print 'Matching %s: %s' % (self,match)
        return []


class Album(Base):

    """Album

    Album of music tracks in tree database.

    """

    __tablename__ = 'albums'

    id = Column(Integer, primary_key=True)

    directory = Column(SafeUnicode)
    tree_id = Column(Integer, ForeignKey('trees.id'), nullable=True)
    tree = relationship('Tree', single_parent=False,
        backref=backref('albums', order_by=directory, cascade='all, delete, delete-orphan')
    )

    def __repr__(self):
        return self.directory

    @property
    def path(self):
        return self.directory

    @property
    def relative_path(self):
        path = self.directory
        if self.tree and path[:len(self.tree.path)]==self.tree.path:
            path = path[len(self.tree.path):].lstrip(os.sep)
        return path

    @property
    def exists(self):
        return os.path.isdir(self.directory)


class Track(Base):

    """Track

    Audio file. Optionally associated with a audio file tree

    """

    __tablename__ = 'tracks'

    id = Column(Integer, primary_key=True)

    directory = Column(SafeUnicode)
    filename = Column(SafeUnicode)
    extension = Column(SafeUnicode)
    checksum = Column(SafeUnicode)
    mtime = Column(Integer)
    deleted = Column(Boolean)

    tree_id = Column(Integer, ForeignKey('trees.id'), nullable=True)
    tree = relationship('Tree', single_parent=False,
        backref=backref('tracks', order_by=[directory, filename], cascade='all, delete, delete-orphan')
    )
    album_id = Column(Integer, ForeignKey('albums.id'), nullable=True)
    album = relationship('Album', single_parent=False,
        backref=backref('tracks', order_by=[directory,filename], cascade='all, delete, delete-orphan')
    )

    def __repr__(self):
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                return os.sep.join([self.directory, self.filename])

    @property
    def path(self):
        return os.path.join(self.directory,self.filename)

    @property
    def relative_path(self):
        path = os.path.join(self.directory,self.filename)
        if self.tree and path[:len(self.tree.path)]==self.tree.path:
            path = path[len(self.tree.path):].lstrip(os.sep)
        return path

    @property
    def exists(self):
        return os.path.isfile(self.path)

    def update_tags(self,session,tags):
        for tag in session.query(Tag).filter(Tag.track == self):
            session.delete(tag)

        for tag,value in tags.items():
            session.add(Tag(track=self,tag=tag,value=value))

class Tag(Base):

    """Tag

    Metadata tag for an audio file

    """

    __tablename__='tags'

    id=Column(Integer, primary_key = True)
    tag=Column(SafeUnicode)
    value=Column(SafeUnicode)
    base64_encoded=Column(Boolean)

    track_id=Column(Integer, ForeignKey('tracks.id'), nullable = False)
    track=relationship('Track', single_parent = False,
        backref = backref('tags', order_by=tag, cascade='all, delete, delete-orphan')
    )

    def __repr__(self):
        return '%s=%s' % (self.tag, self.value)


class MusaDB(object):

    """MusaDB

    Music database storing settings, synchronization data and music tree file metadata

    """

    def __init__(self,path=None,engine=None,debug=False):
        """
        By default, use sqlite databases in file given by path.
        """

        if engine is None:
            if path is None:
                path = DEFAULT_DATABASE

            config_dir = os.path.dirname(path)
            if not os.path.isdir(config_dir):
                try:
                    os.makedirs(config_dir)
                except OSError, (ecode, emsg):
                    raise MusaError('Error creating directory: %s' % config_dir)

            engine = create_engine('sqlite:///%s' % path, encoding='utf-8', echo=debug)

        event.listen(engine, 'connect', self._fk_pragma_on_connect)
        Base.metadata.create_all(engine)

        session_instance = sessionmaker(bind=engine)
        self.session = session_instance()

    def _fk_pragma_on_connect(self, connection, record):
        """Enable foreign keys for sqlite databases"""
        if isinstance(connection, SQLite3Connection):
            cursor = connection.cursor()
            cursor.execute('pragma foreign_keys=ON')
            cursor.close()

    def query(self, *args, **kwargs):
        """Wrapper to do a session query"""
        return self.session.query(*args,**kwargs)

    def rollback(self):
        """Wrapper to rolllback current session query"""
        return self.session.rollback()

    def commit(self):
        """Wrapper to commit current session query"""
        return self.session.commit()

    def as_dict(self, result):
        """Returns current query Base result as dictionary"""
        if not hasattr(result,'__table__'):
            raise ValueError('Not a sqlalchemy ORM result')
        return dict((k.name,getattr(result,k.name)) for k in result.__table__.columns)

    def add(self, items):
        """Add items in query session, committing changes"""

        if isinstance(items,list):
            self.session.add_all(items)
        else:
            self.session.add(items)

        self.session.commit()

    def delete(self, items):
        """Delete items in query session, committing changes"""

        if isinstance(items,list):
            for item in items:
                self.session.delete(item)
        else:
            self.session.delete(items)

        self.session.commit()

    @property
    def playlist_sources(self):

        """Return registered PlaylistSource objects from database"""

        return self.query(PlaylistSource).all()

    @property
    def playlist(self):

        """Return registered Playlist objects from database"""

        return self.query(Playlist).all()


    @property
    def trees(self):

        """Return registered Tree objects from database"""

        return self.query(Tree).all()

    def register_tree_type(self, name, description=''):
        existing = self.query(TreeType).filter(TreeType.name==name).first()
        if existing:
            raise MusaError('Tree type was already registered: %s' % name)

        self.add(TreeType(name=name, description=description))

    def unregister_tree_type(self, name, description=''):
        existing = self.query(TreeType).filter(TreeType.name==name).first()
        if not existing:
            raise MusaError('Tree type was not registered: %s' % name)

        self.delete(existing)

    def register_playlist_source(self,path,name='Playlists'):
        existing = self.query(PlaylistSource).filter(PlaylistSource.path==path).first()
        if existing:
            raise MusaError('Playlist source is already registered: %s' % path)

        self.add(PlaylistSource(path=path,name=name))

    def unregister_playlist_source(self, path):
        existing = self.query(PlaylistSource).filter(PlaylistSource.path==path).first()
        if not existing:
            raise MusaError('Playlist source is not registered: %s' % path)

        self.delete(existing)

    def register_tree(self,path,description='',tree_type='songs'):
        if isinstance(path,str):
            path = unicode(path,'utf-8')

        existing = self.query(Tree).filter(Tree.path==path).first()
        if not existing:
            raise MusaError('Tree was already registered: %s' % path)

        tt = self.get_tree_type(tree_type)
        self.add(Tree(path=path,description=description,type=tt))

    def unregister_tree(self,path,description=''):
        existing = self.query(Tree).filter(Tree.path==path).first()
        if not existing:
            raise MusaError('Tree was not registered: %s' % path)

        self.delete(existing)

    def get_tree_type(self,name):
        return self.query(TreeType).filter(TreeType.name==name).first()

    def get_tree(self,path,tree_type='songs'):
        return self.query(Tree).filter(Tree.path==path).first()

    def get_playlist_source(self,path):
        return self.query(PlaylistSource).filter(PlaylistSource.path==path).first()

    def get_playlist(self,path):
        return self.query(Playlist).filter(Playlist.path==path).first()
