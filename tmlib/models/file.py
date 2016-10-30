# TmLibrary - TissueMAPS library for distibuted image processing routines.
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
import numpy as np
from sqlalchemy import Column, String, Integer, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import UniqueConstraint
from cached_property import cached_property

from tmlib.utils import assert_type
from tmlib.utils import notimplemented
from tmlib.image import ChannelImage
from tmlib.image import IllumstatsImage
from tmlib.image import IllumstatsContainer
from tmlib.metadata import ChannelImageMetadata
from tmlib.metadata import IllumstatsImageMetadata
from tmlib.readers import DatasetReader
from tmlib.readers import ImageReader
from tmlib.writers import DatasetWriter
from tmlib.writers import ImageWriter
from tmlib.models.base import FileModel, DateMixIn
from tmlib.models.status import FileUploadStatus
from tmlib.models.utils import remove_location_upon_delete

logger = logging.getLogger(__name__)


@remove_location_upon_delete
class MicroscopeImageFile(FileModel, DateMixIn):

    '''Image file that was generated by the microscope.
    The file format differs between microscope types and may be vendor specific.
    '''

    __tablename__ = 'microscope_image_files'

    __table_args__ = (UniqueConstraint('name', 'acquisition_id'), )

    __distribute_by_hash__ = 'id'

    #: str: name given by the microscope
    name = Column(String(50), index=True)

    #: str: OMEXML metadata
    omexml = Column(Text)

    #: str: upload status
    status = Column(String(20), index=True)

    #: int: ID of the parent acquisition
    acquisition_id = Column(
        Integer,
        ForeignKey('acquisitions.id', onupdate='CASCADE', ondelete='CASCADE'),
        index=True
    )

    #: tmlib.models.acquisition.Acquisition: parent acquisition
    acquisition = relationship(
        'Acquisition',
        backref=backref('microscope_image_files', cascade='all, delete-orphan')
    )

    def __init__(self, name, acquisition_id):
        '''
        Parameters
        ----------
        name: str
            name of the microscope image file
        acquisition_id: int
            ID of the parent acquisition
        '''
        self.name = name
        self.acquisition_id = acquisition_id
        self.status = FileUploadStatus.WAITING

    @property
    def location(self):
        '''str: location of the file'''
        if self._location is None:
            self._location = os.path.join(
                self.acquisition.microscope_images_location, self.name
            )
        return self._location

    @notimplemented
    def get(self):
        pass

    @notimplemented
    def put(self, data):
        pass

    def to_dict(self):
        '''Returns attributes "id", "name" and "status" as key-value pairs.

        Returns
        -------
        dict
        '''
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status
        }

    def __repr__(self):
        return '<MicroscopeImageFile(id=%r, name=%r)>' % (self.id, self.name)


@remove_location_upon_delete
class MicroscopeMetadataFile(FileModel, DateMixIn):

    '''Metadata file that was generated by the microscope.
    The file format differs between microscope types and may be vendor specific.
    '''

    __tablename__ = 'microscope_metadata_files'

    __table_args__ = (UniqueConstraint('name', 'acquisition_id'), )

    __distribute_by_hash__ = 'id'

    #: str: name given by the microscope
    name = Column(String(50), index=True)

    #: str: upload status
    status = Column(String(20), index=True)

    #: int: ID of the parent acquisition
    acquisition_id = Column(
        Integer,
        ForeignKey('acquisitions.id', onupdate='CASCADE', ondelete='CASCADE'),
        index=True
    )

    #: tmlib.models.acquisition.Acquisition: parent acquisition
    acquisition = relationship(
        'Acquisition',
        backref=backref(
            'microscope_metadata_files', cascade='all, delete-orphan'
        )
    )

    def __init__(self, name, acquisition_id):
        '''
        Parameters
        ----------
        name: str
            name of the file
        acquisition_id: int
            ID of the parent acquisition
        '''
        self.name = name
        self.acquisition_id = acquisition_id
        self.status = FileUploadStatus.WAITING

    @property
    def location(self):
        '''str: location of the file'''
        if self._location is None:
            self._location = os.path.join(
                self.acquisition.microscope_metadata_location, self.name
            )
        return self._location

    @notimplemented
    def get(self):
        pass

    @notimplemented
    def put(self, data):
        pass

    def to_dict(self):
        '''Return attributes "id", "name" and "status" as key-value pairs.

        Returns
        -------
        dict
        '''
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status
        }

    def __repr__(self):
        return '<MicroscopeMetdataFile(id=%r, name=%r)>' % (self.id, self.name)


@remove_location_upon_delete
class ChannelImageFile(FileModel, DateMixIn):

    '''A *channel image file* holds a single 2D pixels plane that was extracted
    from a microscope image file. It represents a unique combination of
    time point, site, and channel.

    '''

    #: str: name of the corresponding database table
    __tablename__ = 'channel_image_files'

    __table_args__ = (
        UniqueConstraint('tpoint', 'site_id', 'cycle_id', 'channel_id'),
    )

    __distribute_by_hash__ = 'id'

    _n_planes = Column('n_planes', Integer, index=True)

    #: int: zero-based index in the time series
    tpoint = Column(Integer, index=True)

    #: int: number of z planes
    n_planes = Column(Integer, index=True)

    #: int: ID of the parent cycle
    cycle_id = Column(
        Integer,
        ForeignKey('cycles.id', onupdate='CASCADE', ondelete='CASCADE'),
        index=True
    )

    #: int: ID of the parent site
    site_id = Column(
        Integer,
        ForeignKey('sites.id', onupdate='CASCADE', ondelete='CASCADE'),
        index=True
    )

    #: int: ID of the parent channel
    channel_id = Column(
        Integer,
        ForeignKey('channels.id', onupdate='CASCADE', ondelete='CASCADE'),
        index=True
    )

    #: tmlib.models.cycle.Cycle: parent cycle
    cycle = relationship(
        'Cycle',
        backref=backref('channel_image_files', cascade='all, delete-orphan')
    )

    #: tmlib.models.site.Site: parent site
    site = relationship(
        'Site',
        backref=backref('channel_image_files', cascade='all, delete-orphan')
    )

    #: tmlib.models.channel.Channel: parent channel
    channel = relationship(
        'Channel',
        backref=backref('image_files', cascade='all, delete-orphan')
    )

    #: Format string for filenames
    FILENAME_FORMAT = 'channel_image_file_{id}.h5'

    def __init__(self, tpoint, site_id, cycle_id, channel_id):
        '''
        Parameters
        ----------
        tpoint: int
            zero-based time point index in the time series
        site_id: int
            ID of the parent site
        cycle_id: int
            ID of the parent cycle
        channel_id: int
            ID of the parent channel
        '''
        self.tpoint = tpoint
        self.site_id = site_id
        self.cycle_id = cycle_id
        self.channel_id = channel_id
        self._n_planes = 0

    def get(self, z=None):
        '''Gets stored image.

        Parameters
        ----------
        z: int, optional
            zero-based z index of an individual pixel plane (default: ``None``)

        Returns
        -------
        tmlib.image.ChannelImage
            image stored in the file
        '''
        metadata = ChannelImageMetadata(
            channel_id=self.channel_id,
            site_id=self.site_id,
            tpoint=self.tpoint,
            cycle_id=self.cycle_id
        )
        if z is not None:
            with DatasetReader(self.location) as f:
                array = f.read('z_%d' % z)
            metadata.zplane = z
        else:
            pixels = list()
            with DatasetReader(self.location) as f:
                datasets = f.list_datasets(pattern='z_\d+')
                for z in datasets:
                    pixels.append(f.read(z))
            array = np.dstack(pixels)
        if self.site.intersection is not None:
            metadata.upper_overhang = self.site.intersection.upper_overhang
            metadata.lower_overhang = self.site.intersection.lower_overhang
            metadata.right_overhang = self.site.intersection.right_overhang
            metadata.left_overhang = self.site.intersection.left_overhang
            shift = [
                s for s in self.site.shifts if s.cycle_id == self.cycle_id
            ][0]
            metadata.x_shift = shift.x
            metadata.y_shift = shift.y
        return ChannelImage(array, metadata)

    @assert_type(image='tmlib.image.ChannelImage')
    def put(self, image, z=None):
        '''Puts image to storage.

        Parameters
        ----------
        image: tmlib.image.ChannelImage
            pixels/voxels data that should be stored in the image file
        z: int, optional
            zero-based z index of an individual pixel plane (default: ``None``)

        Note
        ----
        When no `z` index is provided, the file will be truncated and all
        planes replaced.
        '''
        if z is not None:
            if image.dimensions[2] > 1:
                raise ValueError('Image must be a 2D pixels plane.')
            with DatasetWriter(self.location) as f:
                f.write('z_%d' % z, image.array)
                self.n_planes = len(f.list_datasets(pattern='z_\d+'))
        else:
            with DatasetWriter(self.location, truncate=True) as f:
                for z, plane in image.iter_planes():
                    f.write('z_%d' % z, plane)
            self.n_planes = image.dimensions[2]

    @hybrid_property
    def n_planes(self):
        '''int: number of planes stored in the file'''
        return self._n_planes

    @n_planes.setter
    def n_planes(self, value):
        self._n_planes = value

    @property
    def location(self):
        '''str: location of the file'''
        if self._location is None:
            self._location = os.path.join(
                self.cycle.channel_images_location,
                self.FILENAME_FORMAT.format(id=self.id)
            )
        return self._location

    def __repr__(self):
        return '<%s(id=%r, tpoint=%r, well=%r, y=%r, x=%r, channel=%r)>' % (
            self.__class__.__name__, self.id, self.tpoint,
            self.site.well.name, self.site.y,
            self.site.x, self.channel.index
        )



@remove_location_upon_delete
class IllumstatsFile(FileModel, DateMixIn):

    '''An *illumination statistics file* holds matrices for mean and standard
    deviation values calculated at each pixel position across all images of
    the same *channel* and *cycle*.

    '''

    #: Format string to build filename
    FILENAME_FORMAT = 'illumstats_file_{id}.h5'

    __tablename__ = 'illumstats_files'

    __table_args__ = (UniqueConstraint('channel_id', 'cycle_id'), )

    #: int: ID of parent channel
    channel_id = Column(
        Integer,
        ForeignKey('channels.id', onupdate='CASCADE', ondelete='CASCADE'),
        index=True
    )

    #: int: ID of parent cycle
    cycle_id = Column(
        Integer,
        ForeignKey('cycles.id', onupdate='CASCADE', ondelete='CASCADE'),
        index=True
    )

    #: tmlib.models.channel.Channel: parent channel
    channel = relationship(
        'Channel',
        backref=backref('illumstats_files', cascade='all, delete-orphan')
    )

    #: tmlib.models.cycle.Cycle: parent cycle
    cycle = relationship(
        'Cycle',
        backref=backref('illumstats_files', cascade='all, delete-orphan')
    )

    def __init__(self, channel_id, cycle_id):
        '''
        Parameters
        ----------
        channel_id: int
            ID of the parent channel
        cycle_id: int
            ID of the parent cycle
        '''
        self.channel_id = channel_id
        self.cycle_id = cycle_id

    def get(self):
        '''Get illumination statistics images from store.

        Returns
        -------
        Illumstats
            illumination statistics images
        '''
        logger.debug(
            'get data from illumination statistics file: %s', self.name
        )
        metadata = IllumstatsImageMetadata(
            channel_id=self.channel.id,
            cycle_id=self.cycle.id
        )
        with DatasetReader(self.location) as f:
            mean = IllumstatsImage(f.read('mean'), metadata)
            std = IllumstatsImage(f.read('std'), metadata)
            keys = f.read('percentiles/keys')
            values = f.read('percentiles/values')
            percentiles = dict(zip(keys, values))
        return IllumstatsContainer(mean, std, percentiles).smooth()

    @assert_type(data='tmlib.image.IllumstatsContainer')
    def put(self, data):
        '''Put illumination statistics images to store.

        Parameters
        ----------
        data: IllumstatsContainer
            illumination statistics
        '''
        logger.debug(
            'put data to illumination statistics file: %s', self.location
        )
        with DatasetWriter(self.location, truncate=True) as f:
            f.write('mean', data.mean.array)
            f.write('std', data.std.array)
            f.write('/percentiles/keys', data.percentiles.keys())
            f.write('/percentiles/values', data.percentiles.values())

    @property
    def location(self):
        '''str: location of the file'''
        if self._location is None:
            self._location = os.path.join(
                self.cycle.illumstats_location,
                self.FILENAME_FORMAT.format(id=self.id)
            )
        return self._location

    def __repr__(self):
        return (
            '<IllumstatsFile(id=%r, channel_id=%r)>'
            % (self.id, self.channel_id)
        )
