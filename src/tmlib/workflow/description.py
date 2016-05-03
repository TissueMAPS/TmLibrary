import re
import json
from abc import ABCMeta
from abc import abstractmethod

import tmlib.workflow
from tmlib.utils import assert_type
from tmlib.errors import WorkflowDescriptionError
from tmlib.workflow.registry import get_step_args
from tmlib.workflow.registry import get_step_api
from tmlib.workflow.args import BatchArguments
from tmlib.workflow.args import SubmissionArguments
from tmlib.workflow.args import ExtraArguments
from tmlib.workflow.args import ArgumentMeta


class WorkflowDescription(object):

    '''Abstract base class for the description of a `TissueMAPS` workflow.

    A workflow consists of a sequence of *stages*, which are themselves
    composed of *steps*. Each *step* represents a collection of computational
    jobs, which can be submitted for parallel processing on a cluster.

    See also
    --------
    :py:class:`tmlib.workflow.description.WorkflowStageDescription`
    :py:class:`tmlib.workflow.description.WorkflowStepDescription`
    '''

    __metaclass__ = ABCMeta

    def __init__(self):
        self.stages = list()

    @abstractmethod
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
            :py:class:`tmlib.workflow.description.WorkflowStageDescription`
        '''

    def as_dict(self):
        '''Returns attributes as key-value pairs.

        Returns
        -------
        dict
        '''
        description = dict()
        description['type'] = self.type
        description['stages'] = [s.as_dict() for s in self.stages]
        return description

    def jsonify(self):
        '''Returns attributes as key-value pairs endcoded as JSON.

        Returns
        -------
        str
            JSON string encoding the description of the workflow as a
            mapping of key-value pairs
        '''
        return json.dumps(self.as_dict())


class WorkflowStageDescription(object):

    '''Description of a TissueMAPS workflow stage.'''

    __metaclass__ = ABCMeta

    @assert_type(name='basestring', mode='basestring')
    def __init__(self, name, mode):
        '''
        Parameters
        ----------
        name: str
            name of the stage
        mode: str
            mode of workflow stage submission, i.e. whether steps are submitted
            simultaneously or one after another
            (options: ``{"sequential", "parallel"}``) 

        Raises
        ------
        TypeError
            when `name` or `steps` have the wrong type
        '''
        self.name = str(name)
        self.mode = mode
        if self.mode not in {'parallel', 'sequential'}:
            raise ValueError(
                'Attribute "mode" must be either "parallel" or "sequential"'
            )
        self.steps = list()

    @abstractmethod
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
            :py:class:`tmlib.workflow.description.WorkflowStepDescription`
        '''

    def as_dict(self):
        '''Returns the attributes as key-value pairs.

        Parameters
        ----------
        dict
        '''
        description = dict()
        description['name'] = self.name
        description['mode'] = self.mode
        description['steps'] = [s.as_dict() for s in self.steps]
        return description

    def jsonify(self):
        '''Returns the attributes as key-value pairs encoded as JSON.

        Returns
        -------
        str
            JSON string encoding the description of the stage as a
            mapping of key-value pairs
        '''
        return json.dumps(self.as_dict())


class WorkflowStepDescription(object):

    '''Description of a workflow step.'''

    def __init__(self, name, batch_args=dict(), submission_args=dict(),
            extra_args=dict()):
        '''
        Parameters
        ----------
        name: str
            name of the step
        batch_args: dict, optional
            names and values of batch arguments
        submission_args: dict, optional
            names and values of submission arguments 
        extra_args: dict, optional
            names and values of additional arguments

        Raises
        ------
        WorkflowDescriptionError
            when a provided argument is not a valid argument for the given step
        '''
        self.name = str(name)
        batch_args_cls, submission_args_cls, extra_args_cls = get_step_args(name)
        self.batch_args = batch_args_cls(**batch_args)
        self.submission_args = submission_args_cls(**submission_args)
        self._extra_args = None
        if extra_args_cls is not None:
            self.extra_args = extra_args_cls(**extra_args)

    @property
    def extra_args(self):
        '''tmlib.workflow.args.ExtraArguments: extra arguments instance'''
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
        '''tmlib.workflow.args.BatchArguments: batch arguments instance'''
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

    def as_dict(self):
        '''Returns attributes as key-value pairs.

        Returns
        -------
        dict
        '''
        description = dict()
        description['name'] = self.name
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
        return json.dumps(self.as_dict())