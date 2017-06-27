# TmLibrary - TissueMAPS library for distibuted image analysis routines.
# Copyright (C) 2016  Markus D. Herrmann, University of Zurich and Robin Hafen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import os
import logging
import collections
from io import BytesIO
from struct import pack
import psycopg2
import numpy as np
import pandas as pd
from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean, ForeignKey, Index,
    PrimaryKeyConstraint
)
from sqlalchemy.dialects.postgresql import BYTEA
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.hybrid import hybrid_property

from tmlib.image import PyramidTile
from tmlib.metadata import PyramidTileMetadata
from tmlib.models import ExperimentModel

logger = logging.getLogger(__name__)


class ChannelLayerTile(ExperimentModel):

    '''A *channel layer tile* is a component of an image pyramid. Each tile
    holds a single 2D 8-bit pixel plane with pre-defined dimensions.

    '''

    __tablename__ = 'channel_layer_tiles'

    __table_args__ = (
        PrimaryKeyConstraint('y', 'channel_layer_id', 'z', 'x'),
    )

    __distribution_method__ = 'hash'

    __distribute_by__ = 'y'

    _pixels = Column('pixels', BYTEA)

    #: int: zero-based zoom level index
    z = Column(Integer, nullable=False)

    #: int: zero-based coordinate on vertical axis
    y = Column(Integer, nullable=False)

    #: int: zero-based coordinate on horizontal axis
    x = Column(Integer, nullable=False)

    # TODO: Add polygon geometry for bounding box of pixels to simplify
    # geometric queries. This allow selecting pyramid tiles that contain
    # certain mapobjects, for example. Ultimately, this could be implemented
    # as Postgis raster, but there is no good Python interface for conversion
    # between rasters and numpy arrays.

    #: int: ID of parent channel layer
    channel_layer_id = Column(Integer, nullable=False)

    def __init__(self, z, y, x, channel_layer_id, pixels=None):
        '''
        Parameters
        ----------
        z: int
            zero-based zoom level index
        y: int
            zero-based row index of the tile at given zoom level
        x: int
            zero-based column index of the tile at given zoom level
        channel_layer_id: int
            ID of the parent channel pyramid
        pixels: tmlib.image.PyramidTile, optional
            pixels array (default: ``None``)
        '''
        self.y = y
        self.x = x
        self.z = z
        self.channel_layer_id = channel_layer_id
        self.pixels = pixels

    @hybrid_property
    def pixels(self):
        '''tmlib.image.PyramidTile: pixel array'''
        # TODO: consider creating a custom SQLAlchemy column type
        metadata = PyramidTileMetadata(
            z=self.z, y=self.y, x=self.x,
            channel_layer_id=self.channel_layer_id
        )
        return PyramidTile.create_from_binary(self._pixels, metadata)

    @pixels.setter
    def pixels(self, value):
        # It might be better to use Postgis raster format, but there don't
        # seem to be good solutions for inserting raster data via Python
        # using numpy arrays at the moment.
        # We may also want to use a smaller tile size. This would work better
        # with the raster format and also play nicer with PostgreSQL BYTEA
        # column type, because values would take less space and therefore
        # wouldn't require TOAST which will probably improve performance.
        # In case we switch to raster tiles, we should also think of a way to
        # colocate tiles and mapobjects on the same shards to improve
        # performance of combined spatial queries.
        if value is not None:
            self._pixels = value.jpeg_encode()
        else:
            self._pixels = None

    @classmethod
    def add(cls, connection, tile):
        '''Adds a new object.

        Parameters
        ----------
        connection: psycopg2.extras.NamedTupleCursor
            experiment-specific database connection created via
            :class:`ExperimentConnection <tmlib.models.utils.ExperimentConnection>`
        tile: tmlib.models.tile.ChannelLayerTile

        Note
        ----
        This performs an *upsert* operation, i.e. *inserts* the tile in case
        it doesn't exist yet and *updates* it otherwise.
        '''
        # Upsert the tile entry, i.e. insert or update if exists
        connection.execute('''
            INSERT INTO channel_layer_tiles AS t (
                channel_layer_id, z, y, x, pixels
            )
            VALUES (%(channel_layer_id)s, %(z)s, %(y)s, %(x)s, %(pixels)s)
            ON CONFLICT ON CONSTRAINT channel_layer_tiles_pkey
            DO UPDATE SET pixels = %(pixels)s
        ''', {
            'channel_layer_id': tile.channel_layer_id,
            'z': tile.z, 'y': tile.y, 'x': tile.x,
            'pixels': psycopg2.Binary(tile._pixels.tostring())
        })

    @classmethod
    def add_multiple(cls, connection, tiles):
        '''Adds multiple objects at once.

        Parameters
        ----------
        connection: psycopg2.extras.NamedTupleCursor
            experiment-specific database connection created via
            :class:`ExperimentConnection <tmlib.models.utils.ExperimentConnection>`
        tiles: List[tmlib.models.tile.ChannelLayerTile]

        Warning
        -------
        This does not update existing tiles and will raise an error in case
        a tile already exists in the database.
        '''
        # TODO: Figure out how to COPY BYTEA correctly as binary and then
        # group tiles by "y" (the distribution key) and COPY them en bulk.
        for tile in tiles:
            connection.execute('''
                INSERT INTO channel_layer_tiles AS t (
                    channel_layer_id, z, y, x, pixels
                )
                VALUES (%(channel_layer_id)s, %(z)s, %(y)s, %(x)s, %(pixels)s)
            ''', {
                'channel_layer_id': tile.channel_layer_id,
                'z': tile.z, 'y': tile.y, 'x': tile.x,
                'pixels': psycopg2.Binary(tile._pixels.tostring())
            })

    def __repr__(self):
        return '<%s(z=%r, y=%r, x=%r, channel_layer_id=%r)>' % (
            self.__class__.__name__, self.z, self.y, self.x,
            self.channel_layer_id
        )


