__version__ = "0.12.2"

from .api import *
from .ast import *
from .literals import *
from .node import *
from .operations import *
from .optimizer import *
from .plugin import *
from .resolver import *
from .serializer import *
from .sources import *
from .utils import *


def __monkey_patch():
    from nbtlib import Compound, List

    def __patched_hash(self):
        return hash(str(self))

    Compound.__hash__ = __patched_hash
    List.__hash__ = __patched_hash


__monkey_patch()
