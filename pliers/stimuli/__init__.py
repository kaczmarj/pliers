from abc import ABCMeta, abstractmethod, abstractproperty
from os.path import exists, isdir, join, basename
from glob import glob
from six import with_metaclass, string_types
import importlib
from collections import namedtuple
from pliers import config
import pandas as pd


__all__ = ['audio', 'image', 'text', 'video']


class Stim(with_metaclass(ABCMeta)):

    ''' Base Stim class. '''
    def __init__(self, filename=None, onset=None, duration=None, name=None):

        self.filename = filename
        self.onset = onset
        self.duration = duration
        self._history = None

        if name is None:
            name = '' if self.filename is None else basename(self.filename)
        self.name = name

    @property
    def history(self):
        return self._history

    @history.setter
    def history(self, history):
        self._history = history


class CollectionStimMixin(with_metaclass(ABCMeta)):

    @abstractmethod
    def __iter__(self):
        pass


def _get_stim_class(name):

    name = name.lower().replace('_', '')

    if not name.endswith('stim'):
        name += 'stim'

    # Recursively get all classes that inherit from the passed base class
    def get_subclasses(cls):
        subclasses = []
        for sc in cls.__subclasses__():
            subclasses.append(sc)
            subclasses.extend(get_subclasses(sc))
        return subclasses

    # Import all submodules so we have a comprehensive list of Stims
    base = Stim
    bm = base.__module__
    submods = importlib.import_module(bm).__all__
    sources = ['%s.%s' % (bm, sm) for sm in submods]
    [importlib.import_module(s) for s in sources]

    stims = get_subclasses(base)
    for a in stims:
        if a.__name__.lower().split('.')[-1] == name.lower():
            return a

    raise KeyError("No Stim class matches '%s' (case-insensitive)." % name)


def load_stims(source, dtype=None):
    """ Load one or more stimuli directly from file, inferring/extracting
    metadata as needed.
    Args:
        source (str or list): The location to load the stim(s) from. Can be
            the path to a directory, to a single file, or a list of filenames.
        dtype (str): The type of stim to load. If dtype is None, relies on the
            filename extension for guidance. If dtype is provided, must be
            one of 'video', 'image', 'audio', or 'text'.
    Returns: A list of Stims.
    """
    import magic
    from .video import VideoStim, ImageStim
    from .audio import AudioStim
    from .text import TextStim

    if isinstance(source, string_types):
        source = [source]

    source = [s for s in source if exists(s)]

    stims = []

    def load_file(source):
        mime = magic.from_file(source, mime=True)
        if not isinstance(mime, string_types):
            mime = mime.decode('utf-8')
        mime = mime.split('/')[0]
        stim_map = {
            'image': ImageStim,
            'video': VideoStim,
            'text': TextStim,
            'audio': AudioStim
        }
        if mime in stim_map.keys():
            s = stim_map[mime](source)
            stims.append(s)

    for s in source:
        if isdir(s):
            for f in glob(join(s, '*')):
                load_file(f)
        else:
            load_file(s)

    return stims


def _log_transformation(source, result, trans=None):

    if not config.transformation_history:
        return

    values = [source.name, source.filename, source.__class__.__name__]
    if isinstance(result, Stim):
        values.extend([result.name, result.filename])
    else:
        values.extend(['', ''])
    values.append(result.__class__.__name__)
    if trans is not None:
        values.append(trans.__class__.__name__)
        tr_attrs = [getattr(trans, attr) for attr in trans._log_attributes]
        values.append(str(dict(zip(trans._log_attributes, tr_attrs))))
    else:
        values.append(['', ''])
    parent = source.history
    string = str(parent) if parent else values[2]
    string += '->%s/%s' % (values[6], values[5])
    values.extend([string, parent])
    result.history = TransformationLog(*values)


class TransformationLog(namedtuple('TransformationLog', "source_name source_file " +
                             "source_class result_name result_file result_class " +
                             " transformer_class transformer_params string parent")):
    '''A namedtuple that stores information about a single transformation. '''

    __slots__ = ()

    def __str__(self):
        return self.string

    def to_df(self):
        def _append_row(rows, history):
            rows.append(history[:-2])
            if history[-1]:
                _append_row(rows, history[-1])
            return rows
        rows = _append_row([], self)[::-1]
        return pd.DataFrame(rows, columns=self._fields[:-2])
