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

import tmlib.models as tm
from tmlib.utils import notimplemented
from tmlib.image import IllumstatsContainer
from tmlib.models.utils import delete_location
from tmlib.workflow.api import ClusterRoutines
from tmlib.workflow.corilla.stats import OnlineStatistics
from tmlib.workflow import register_step_api

logger = logging.getLogger(__name__)


@register_step_api('corilla')
class IllumstatsCalculator(ClusterRoutines):

    '''Class for calculating illumination statistics.'''

    def __init__(self, experiment_id, verbosity):
        '''
        Parameters
        ----------
        experiment_id: int
            ID of parent experiment
        verbosity: int
            logging level
        '''
        super(IllumstatsCalculator, self).__init__(experiment_id, verbosity)

    def create_batches(self, args):
        '''Creates job descriptions for parallel computing.

        Parameters
        ----------
        args: tmlib.corilla.args.CorillaInitArgs
            step-specific arguments

        Returns
        -------
        Dict[str, List[dict] or dict]
            job descriptions
        '''
        job_descriptions = dict()
        job_descriptions['run'] = list()
        count = 0

        with tm.utils.ExperimentSession(self.experiment_id) as session:

            # NOTE: Illumination statistics are calculated for each cycle
            # separately. This should be safer, since imaging condition might
            # differ between cycles. 

            # TODO: Enable pooling image files across cycles, which may be
            # necessary to get enough images for robust statistics in case
            # each cycle has only a few images.
            for cycle in session.query(tm.Cycle):

                for channel in session.query(tm.Channel):

                    files = [
                        f for f in cycle.channel_image_files
                        if f.channel_id == channel.id
                    ]

                    if not files:
                        continue

                    count += 1
                    job_descriptions['run'].append({
                        'id': count,
                        'inputs': {
                            'channel_image_files': [
                                f.location for f in files
                            ]
                        },
                        'outputs': {},
                        'channel_image_files_ids': [
                            f.id for f in files
                        ],
                        'channel_id': channel.id,
                        'cycle_id': cycle.id
                    })
        return job_descriptions

    def delete_previous_job_output(self):
        '''Deletes all :class:`tmlib.models.file.IllumstatsFile` instances
        of the processed experiment.
        '''
        logger.info('delete existing illumination statistics files')
        with tm.utils.ExperimentSession(self.experiment_id) as session:
            session.query(tm.IllumstatsFile).delete()

    def run_job(self, batch):
        '''Calculates illumination statistics.

        Parameters
        ----------
        batch: dict
            job description
        '''
        file_ids = batch['channel_image_files_ids']
        logger.info('calculate illumination statistics')
        with tm.utils.ExperimentSession(self.experiment_id) as session:
            file = session.query(tm.ChannelImageFile).get(file_ids[0])
            img = file.get(z=0)
        stats = OnlineStatistics(image_dimensions=img.dimensions[0:2])
        for fid in file_ids:
            with tm.utils.ExperimentSession(self.experiment_id) as session:
                file = session.query(tm.ChannelImageFile).get(fid)
                logger.info('update statistics for image: %d', file.id)
                for z in xrange(file.n_planes):
                    img = file.get(z=z)
                    stats.update(img)

        with tm.utils.ExperimentSession(self.experiment_id) as session:
            stats_file = session.get_or_create(
                tm.IllumstatsFile,
                channel_id=batch['channel_id'], cycle_id=batch['cycle_id']
            )
            logger.info('write calculated statistics to file')
            illumstats = IllumstatsContainer(
                stats.mean, stats.std, stats.percentiles
            )
            stats_file.put(illumstats)

    @notimplemented
    def collect_job_output(self, batch):
        pass
