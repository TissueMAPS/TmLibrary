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
import re
import json

import tmlib.workflow
from tmlib.utils import assert_type
from tmlib.errors import WorkflowDescriptionError
from tmlib.workflow import get_step_args
from tmlib.workflow import get_step_api
from tmlib.workflow import get_step_information
from tmlib.workflow import get_workflow_dependencies
from tmlib.workflow.args import BatchArguments
from tmlib.workflow.args import SubmissionArguments
from tmlib.workflow.args import ExtraArguments
from tmlib.workflow.args import ArgumentMeta


class WorkflowDescription(object):

    '''Description of a `TissueMAPS` workflow.

    A workflow consists of a sequence of *stages*, which are themselves
    composed of *steps*. Each *step* represents a collection of computational
    jobs, which can be submitted for parallel processing on a cluster.

    In principle, workflow steps can be arranged in arbitrary order and
    interdependencies between steps are checked dynamically while the workflow
    progresses. If a dependency is not fullfilled upon progression to the
    next step, i.e. if a required input has not been generated by another
    upstream step, the workflow will stop.

    '''

    def __init__(self, type, stages=None):
        '''
        Parameters
        ----------
        type: str
            type of the workflow
        stages: List[dict]
            description of workflow stages as key-value pairs

        Note
        ----
        There must be a Python module that declares the dependencies
        for the given `type`.
        '''
        self.type = type
        self.dependencies = get_workflow_dependencies(self.type)
        self.stages = list()
        if stages is not None:
            for stage in stages:
                self.add_stage(WorkflowStageDescription(self.type, **stage))
        else:
            for name in self.dependencies.STAGES:
                mode = self.dependencies.STAGE_MODES[name]
                stage = {'name': name, 'mode': mode, 'active': True}
                self.add_stage(WorkflowStageDescription(self.type, **stage))

    def add_stage(self, stage_description):
        '''Adds an additional stage to the workflow.

        Parameters
        ----------
        stage_description: tmlib.workflow.description.WorkflowStageDescription
            description of the stage that should be added

        Raises
        ------
        TypeError
            when `stage_description` doesn't have type
            :class:`tmlib.workflow.description.WorkflowStageDescription`
        '''
        if not isinstance(stage_description, WorkflowStageDescription):
            raise TypeError(
                'Argument "stage_description" must have type '
                'tmlib.workflow.description.WorkflowStageDescription.'
            )
        for stage in self.stages:
            if stage.name == stage_description.name:
                raise WorkflowDescriptionError(
                    'Stage "%s" already exists.' % stage_description.name
                )
        if stage_description.name not in self.dependencies.STAGES:
            raise WorkflowDescriptionError(
                'Unknown stage "%s". Implemented stages are: "%s"'
                % (stage_description.name,
                    '", "'.join(self.dependencies.STAGES))
            )
        for step in stage_description.steps:
            implemented_steps = self.dependencies.STEPS_PER_STAGE[
                stage_description.name
            ]
            if step.name not in implemented_steps:
                raise WorkflowDescriptionError(
                    'Unknown step "%s" for stage "%s". '
                    'Implemented steps are: "%s"'
                    % (step.name, stage_description.name,
                        '", "'.join(implemented_steps))
                )
        stage_names = [s.name for s in self.stages]
        if stage_description.name in self.dependencies.INTER_STAGE_DEPENDENCIES:
            for dep in self.dependencies.INTER_STAGE_DEPENDENCIES[stage_description.name]:
                if dep not in stage_names:
                    logger.warning(
                        'stage "%s" requires upstream stage "%s"',
                        stage_description.name, dep
                    )
        for name in stage_names:
            if stage_description.name in self.dependencies.INTER_STAGE_DEPENDENCIES[name]:
                raise WorkflowDescriptionError(
                    'Stage "%s" must be upstream of stage "%s".'
                    % (stage_description.name, name)
                )
        step_names = [s.name for s in stage_description.steps]
        required_steps = self.dependencies.STEPS_PER_STAGE[stage_description.name]
        for name in step_names:
            if name not in required_steps:
                raise WorkflowDescriptionError(
                    'Stage "%s" requires the following steps: "%s" '
                    % '", "'.join(required_steps)
                )
        self.stages.append(stage_description)

    def to_dict(self):
        '''Returns attributes as key-value pairs.

        Returns
        -------
        dict
        '''
        description = dict()
        description['type'] = self.type
        description['stages'] = [s.to_dict() for s in self.stages]
        return description

    def jsonify(self):
        '''Returns attributes as key-value pairs endcoded as JSON.

        Returns
        -------
        str
            JSON string encoding the description of the workflow as a
            mapping of key-value pairs
        '''
        return json.dumps(self.to_dict())


class WorkflowStageDescription(object):

    '''Description of a TissueMAPS workflow stage.'''

    @assert_type(name='basestring', mode='basestring')
    def __init__(self, type, name, mode, active, steps=None):
        '''
        Parameters
        ----------
        type: str
            name of the workflow type
        name: str
            name of the stage
        mode: str
            mode of workflow stage submission, i.e. whether steps are submitted
            simultaneously or one after another
            (options: ``{"sequential", "parallel"}``)
        active: bool
            whether the stage should be processed
        steps: List[dict]
            description of steps in form of key-value pairs

        Raises
        ------
        TypeError
            when `name` or `steps` have the wrong type
        '''
        self.type = type
        self.dependencies = get_workflow_dependencies(self.type)
        self.name = str(name)
        self.mode = mode
        self.active = active
        if self.mode not in {'parallel', 'sequential'}:
            raise ValueError(
                'Attribute "mode" must be either "parallel" or "sequential"'
            )
        self.steps = list()
        if steps is not None:
            for step in steps:
                BatchArgs, SubmissionArgs, ExtraArgs = get_step_args(
                    step['name']
                )
                batch_arg_values = {
                    a['name']: a['value'] for a in step['batch_args']
                }
                batch_args = BatchArgs(**batch_arg_values)
                submission_arg_values = {
                    a['name']: a['value'] for a in step['submission_args']
                }
                submission_args = SubmissionArgs(**submission_arg_values)
                # NOTE: not every step has extra arguments
                if ExtraArgs is not None:
                    extra_arg_values = {
                        a['name']: a['value'] for a in step['extra_args']
                    }
                    extra_args = ExtraArgs(**extra_arg_values)
                else:
                    extra_args = None
                self.add_step(
                    WorkflowStepDescription(
                        step['name'], step['active'],
                        batch_args, submission_args, extra_args
                    )
                )
        else:
            for name in self.dependencies.STEPS_PER_STAGE[self.name]:
                self.add_step(
                    WorkflowStepDescription(name, True)
                )

    def add_step(self, step_description):
        '''Adds an additional step to the stage.

        Parameters
        ----------
        step_description: tmlib.workflow.description.WorkflowStepDescription
            description of the step that should be added

        Raises
        ------
        TypeError
            when `step_description` doesn't have type
            :class:`tmlib.workflow.description.WorkflowStepDescription`
        '''
        if not isinstance(step_description, WorkflowStepDescription):
            raise TypeError(
                'Argument "step_description" must have type '
                'tmlib.workflow.descripion.WorkflowStepDescription.'
            )
        for step in self.steps:
            if step.name == step_description.name:
                raise WorkflowDescriptionError(
                    'Step "%s" already exists.' % step_description.name
                )
        steps = self.dependencies.STEPS_PER_STAGE[self.name]
        if step_description.name not in steps:
            raise WorkflowDescriptionError(
                'Unknown step "%s" for stage "%s". Known steps are: "%s"'
                % (step_description.name, self.name, '", "'.join(steps))
            )
        name = step_description.name
        step_names = [s.name for s in self.steps]
        if name in self.dependencies.INTRA_STAGE_DEPENDENCIES:
            for dep in self.dependencies.INTRA_STAGE_DEPENDENCIES[name]:
                if dep not in step_names:
                    raise WorkflowDescriptionError(
                        'Step "%s" requires upstream step "%s".' % (name, dep)
                    )
        self.steps.append(step_description)

    def to_dict(self):
        '''Returns the attributes as key-value pairs.

        Parameters
        ----------
        dict
        '''
        description = dict()
        description['name'] = self.name
        description['mode'] = self.mode
        description['active'] = self.active
        description['steps'] = [s.to_dict() for s in self.steps]
        return description

    def jsonify(self):
        '''Returns the attributes as key-value pairs encoded as JSON.

        Returns
        -------
        str
            JSON string encoding the description of the stage as a
            mapping of key-value pairs
        '''
        return json.dumps(self.to_dict())


class WorkflowStepDescription(object):

    '''Description of a workflow step.'''

    def __init__(self, name, active, batch_args=None, submission_args=None,
            extra_args=None):
        '''
        Parameters
        ----------
        name: str
            name of the step
        active: bool
            whether the step should be processed
        batch_args: tmlib.workflow.args.BatchArguments, optional
            batch arguments
        submission_args: tmlib.workflow.args.SubmissionArguments, optional
            submission arguments
        extra_args: tmlib.workflow.args.ExtraArguments, optional
            extra arguments (only some steps have such arguments)

        Raises
        ------
        WorkflowDescriptionError
            when a provided argument is not a valid argument for the given step
        '''
        self.name = str(name)
        self.fullname, self.help = get_step_information(name)
        self.active = active
        BatchArgs, SubmissionArgs, ExtraArgs = get_step_args(name)
        if batch_args is None:
            self.batch_args = BatchArgs()
        else:
            self.batch_args = batch_args
        if submission_args is None:
            self.submission_args = SubmissionArgs()
        else:
            self.submission_args = submission_args
        if extra_args is None:
            if ExtraArgs is not None:
                self.extra_args = ExtraArgs()
            else:
                self._extra_args = None
        else:
            self.extra_args = extra_args

    @property
    def extra_args(self):
        '''tmlib.workflow.args.ExtraArguments: extra arguments'''
        return self._extra_args

    @extra_args.setter
    def extra_args(self, value):
        if not isinstance(value, ExtraArguments):
            raise TypeError(
                'Attribute "extra_args" must have type '
                'tmlib.workflow.args.ExtraArguments'
            )
        self._extra_args = value

    @property
    def batch_args(self):
        '''tmlib.workflow.args.BatchArguments: batch arguments'''
        return self._batch_args

    @batch_args.setter
    def batch_args(self, value):
        if not isinstance(value, BatchArguments):
            raise TypeError(
                'Attribute "batch_args" must have type '
                'tmlib.workflow.args.BatchArguments'
            )
        self._batch_args = value

    @property
    def submission_args(self):
        '''tmlib.workflow.args.BatchArguments: batch arguments instance'''
        return self._submission_args

    @submission_args.setter
    def submission_args(self, value):
        if not isinstance(value, SubmissionArguments):
            raise TypeError(
                'Attribute "submission_args" must have type '
                'tmlib.workflow.args.SubmissionArguments'
            )
        self._submission_args = value

    def to_dict(self):
        '''Returns attributes as key-value pairs.

        Returns
        -------
        dict
        '''
        description = dict()
        description['name'] = self.name
        description['fullname'] = self.fullname
        description['help'] = self.help
        description['active'] = self.active
        description['batch_args'] = self.batch_args.as_list()
        description['submission_args'] = self.submission_args.as_list()
        if self.extra_args is not None:
            description['extra_args'] = self.extra_args.as_list()
        else:
            description['extra_args'] = None
        return description

    def jsonify(self):
        '''Returns attributes as key-value pairs encoded as JSON.

        Returns
        -------
        str
            JSON string encoding the description of the step as a
            mapping of key-value pairs
        '''
        return json.dumps(self.to_dict())
