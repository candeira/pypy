import sys

from pypy.interpreter.baseobjspace import W_Root, SpaceCache
from pypy.rpython.lltypesystem import rffi, lltype
from pypy.module.cpyext.api import cpython_api, bootstrap_function, \
     PyObject, PyObjectP, ADDR, CANNOT_FAIL, \
     Py_TPFLAGS_HEAPTYPE, PyTypeObjectPtr
from pypy.module.cpyext.state import State
from pypy.objspace.std.typeobject import W_TypeObject
from pypy.rlib.objectmodel import specialize, we_are_translated
from pypy.rpython.annlowlevel import llhelper

#________________________________________________________
# type description

class BaseCpyTypedescr(object):
    basestruct = PyObject.TO

    def get_dealloc(self, space):
        raise NotImplementedError
    def allocate(self, space, w_type, itemcount=0):
        raise NotImplementedError
    def make_ref(self, space, w_type, w_obj, itemcount=0):
        raise NotImplementedError
    def attach(self, space, pyobj, w_obj):
        raise NotImplementedError
    def realize(self, space, ref):
        raise NotImplementedError

typedescr_cache = {}

def make_typedescr(typedef, **kw):
    """NOT_RPYTHON

    basestruct: The basic structure to allocate
    alloc     : allocate and basic initialization of a raw PyObject
    attach    : Function called to tie a raw structure to a pypy object
    realize   : Function called to create a pypy object from a raw struct
    dealloc   : a cpython_api(external=False), similar to PyObject_dealloc
    """

    tp_basestruct = kw.pop('basestruct', PyObject.TO)
    tp_make_ref   = kw.pop('make_ref', None)
    tp_attach     = kw.pop('attach', None)
    tp_realize    = kw.pop('realize', None)
    tp_dealloc    = kw.pop('dealloc', None)
    assert not kw, "Extra arguments to make_typedescr"

    null_dealloc = lltype.nullptr(lltype.FuncType([PyObject], lltype.Void))

    class CpyTypedescr(BaseCpyTypedescr):
        basestruct = tp_basestruct
        realize = tp_realize

        def get_dealloc(self, space):
            if tp_dealloc:
                return llhelper(
                    tp_dealloc.api_func.functype,
                    tp_dealloc.api_func.get_wrapper(space))
            else:
                from pypy.module.cpyext.typeobject import subtype_dealloc
                return llhelper(
                    subtype_dealloc.api_func.functype,
                    subtype_dealloc.api_func.get_wrapper(space))

        def allocate(self, space, w_type, itemcount=0):
            # similar to PyType_GenericAlloc?
            # except that it's not related to any pypy object.

            pytype = rffi.cast(PyTypeObjectPtr, make_ref(space, w_type))
            # Don't increase refcount for non-heaptypes
            if pytype:
                flags = rffi.cast(lltype.Signed, pytype.c_tp_flags)
                if not flags & Py_TPFLAGS_HEAPTYPE:
                    Py_DecRef(space, w_type)

            if pytype:
                size = pytype.c_tp_basicsize
            else:
                size = rffi.sizeof(tp_basestruct)
            if itemcount:
                size += itemcount * pytype.c_tp_itemsize
            buf = lltype.malloc(rffi.VOIDP.TO, size,
                                flavor='raw', zero=True)
            pyobj = rffi.cast(PyObject, buf)
            pyobj.c_ob_refcnt = 1
            pyobj.c_ob_type = pytype
            return pyobj

        # Specialized by meta-type
        if tp_make_ref:
            def make_ref(self, space, w_type, w_obj, itemcount=0):
                return tp_make_ref(space, w_type, w_obj, itemcount=itemcount)
        else:
            def make_ref(self, space, w_type, w_obj, itemcount=0):
                typedescr = get_typedescr(w_obj.typedef)
                w_type = space.type(w_obj)
                py_obj = typedescr.allocate(space, w_type, itemcount=itemcount)
                typedescr.attach(space, py_obj, w_obj)
                return py_obj

        if tp_attach:
            def attach(self, space, pyobj, w_obj):
                tp_attach(space, pyobj, w_obj)
        else:
            def attach(self, space, pyobj, w_obj):
                pass

        if tp_realize:
            def realize(self, space, ref):
                return tp_realize(space, ref)
        else:
            def realize(self, space, ref):
                # For most types, a reference cannot exist without
                # a real interpreter object
                raise InvalidPointerException(str(ref))
    if typedef:
        CpyTypedescr.__name__ = "CpyTypedescr_%s" % (typedef.name,)

    typedescr_cache[typedef] = CpyTypedescr()

@bootstrap_function
def init_pyobject(space):
    from pypy.module.cpyext.object import PyObject_dealloc
    # typedescr for the 'object' type
    make_typedescr(space.w_object.instancetypedef,
                   dealloc=PyObject_dealloc)
    # almost all types, which should better inherit from object.
    make_typedescr(None)

@specialize.memo()
def _get_typedescr_1(typedef):
    try:
        return typedescr_cache[typedef]
    except KeyError:
        if typedef.base is not None:
            return _get_typedescr_1(typedef.base)
        return typedescr_cache[None]

def get_typedescr(typedef):
    if typedef is None:
        return typedescr_cache[None]
    else:
        return _get_typedescr_1(typedef)

#________________________________________________________
# refcounted object support

class RefcountState:
    def __init__(self, space):
        self.space = space
        self.py_objects_w2r = {} # { w_obj -> raw PyObject }
        self.py_objects_r2w = {} # { addr of raw PyObject -> w_obj }

        self.borrow_mapping = {None: {}}
        # { w_container -> { w_containee -> None } }
        # the None entry manages references borrowed during a call to
        # generic_cpy_call()
        self.borrowed_objects = {}
        # { addr of containee -> None }

        # For tests
        self.non_heaptypes_w = []

    def _freeze_(self):
        assert not self.borrowed_objects
        assert self.borrow_mapping == {None: {}}
        self.py_objects_r2w.clear() # is not valid anymore after translation
        return False

    def init_r2w_from_w2r(self):
        """Rebuilds the dict py_objects_r2w on startup"""
        for w_obj, obj in self.py_objects_w2r.items():
            ptr = rffi.cast(ADDR, obj)
            self.py_objects_r2w[ptr] = w_obj

    def print_refcounts(self):
        print "REFCOUNTS"
        for w_obj, obj in self.py_objects_w2r.items():
            print "%r: %i" % (w_obj, obj.c_ob_refcnt)

    def make_borrowed(self, w_container, w_borrowed):
        """
        Create a borrowed reference, which will live as long as the container
        has a living reference (as a PyObject!)
        """
        ref = make_ref(self.space, w_borrowed)
        obj_ptr = rffi.cast(ADDR, ref)
        if obj_ptr not in self.borrowed_objects:
            # borrowed_objects owns the reference
            self.borrowed_objects[obj_ptr] = None
        else:
            Py_DecRef(self.space, ref) # already in borrowed list

        borrowees = self.borrow_mapping.setdefault(w_container, {})
        borrowees[w_borrowed] = None
        return ref

    def reset_borrowed_references(self):
        "Used in tests"
        while self.borrowed_objects:
            addr, _ = self.borrowed_objects.popitem()
            w_obj = self.py_objects_r2w[addr]
            Py_DecRef(self.space, w_obj)
        self.borrow_mapping = {None: {}}

    def delete_borrower(self, w_obj):
        """
        Called when a potential container for borrowed references has lost its
        last reference.  Removes the borrowed references it contains.
        """
        if w_obj in self.borrow_mapping: # move to lifeline __del__
            for w_containee in self.borrow_mapping[w_obj]:
                self.forget_borrowee(w_containee)
            del self.borrow_mapping[w_obj]

    def swap_borrow_container(self, container):
        """switch the current default contained with the given one."""
        if container is None:
            old_container = self.borrow_mapping[None]
            self.borrow_mapping[None] = {}
            return old_container
        else:
            old_container = self.borrow_mapping[None]
            self.borrow_mapping[None] = container
            for w_containee in old_container:
                self.forget_borrowee(w_containee)

    def forget_borrowee(self, w_obj):
        "De-register an object from the list of borrowed references"
        ref = self.py_objects_w2r.get(w_obj, lltype.nullptr(PyObject.TO))
        if not ref:
            if DEBUG_REFCOUNT:
                print >>sys.stderr, "Borrowed object is already gone:", \
                      hex(containee)
            return

        containee_ptr = rffi.cast(ADDR, ref)
        try:
            del self.borrowed_objects[containee_ptr]
        except KeyError:
            pass
        else:
            Py_DecRef(self.space, ref)

class InvalidPointerException(Exception):
    pass

DEBUG_REFCOUNT = False

def debug_refcount(*args, **kwargs):
    frame_stackdepth = kwargs.pop("frame_stackdepth", 2)
    assert not kwargs
    frame = sys._getframe(frame_stackdepth)
    print >>sys.stderr, "%25s" % (frame.f_code.co_name, ),
    for arg in args:
        print >>sys.stderr, arg,
    print >>sys.stderr

def create_ref(space, w_obj, items=0):
    """
    Allocates a PyObject, and fills its fields with info from the given
    intepreter object.
    """
    w_type = space.type(w_obj)
    metatypedescr = get_typedescr(w_type.typedef)
    return metatypedescr.make_ref(space, w_type, w_obj, itemcount=items)

def track_reference(space, py_obj, w_obj, replace=False):
    """
    Ties together a PyObject and an interpreter object.
    """
    # XXX looks like a PyObject_GC_TRACK
    ptr = rffi.cast(ADDR, py_obj)
    state = space.fromcache(RefcountState)
    if DEBUG_REFCOUNT:
        debug_refcount("MAKREF", py_obj, w_obj)
        if not replace:
            assert w_obj not in state.py_objects_w2r
        assert ptr not in state.py_objects_r2w
        assert ptr not in state.borrowed_objects
    state.py_objects_w2r[w_obj] = py_obj
    if ptr: # init_typeobject() bootstraps with NULL references
        state.py_objects_r2w[ptr] = w_obj

def make_ref(space, w_obj):
    """
    Returns a new reference to an intepreter object.
    """
    if w_obj is None:
        return lltype.nullptr(PyObject.TO)
    assert isinstance(w_obj, W_Root)
    state = space.fromcache(RefcountState)
    try:
        py_obj = state.py_objects_w2r[w_obj]
    except KeyError:
        py_obj = create_ref(space, w_obj)
        track_reference(space, py_obj, w_obj)
    else:
        Py_IncRef(space, py_obj)
    return py_obj


def from_ref(space, ref):
    """
    Finds the interpreter object corresponding to the given reference.  If the
    object is not yet realized (see stringobject.py), creates it.
    """
    assert lltype.typeOf(ref) == PyObject
    if not ref:
        return None
    state = space.fromcache(RefcountState)
    ptr = rffi.cast(ADDR, ref)

    try:
        return state.py_objects_r2w[ptr]
    except KeyError:
        pass

    # This reference is not yet a real interpreter object.
    # Realize it.
    ref_type = rffi.cast(PyObject, ref.c_ob_type)
    if ref_type == ref:
        raise InvalidPointerException(str(ref))
    w_type = from_ref(space, ref_type)
    assert isinstance(w_type, W_TypeObject)
    return get_typedescr(w_type.instancetypedef).realize(space, ref)


# XXX Optimize these functions and put them into macro definitions
@cpython_api([PyObject], lltype.Void)
def Py_DecRef(space, obj):
    if not obj:
        return
    assert lltype.typeOf(obj) == PyObject

    obj.c_ob_refcnt -= 1
    if DEBUG_REFCOUNT:
        debug_refcount("DECREF", obj, obj.c_ob_refcnt, frame_stackdepth=3)
    if obj.c_ob_refcnt == 0:
        state = space.fromcache(RefcountState)
        ptr = rffi.cast(ADDR, obj)
        if ptr not in state.py_objects_r2w:
            # this is a half-allocated object, lets call the deallocator
            # without modifying the r2w/w2r dicts
            _Py_Dealloc(space, obj)
        else:
            w_obj = state.py_objects_r2w[ptr]
            del state.py_objects_r2w[ptr]
            w_type = space.type(w_obj)
            if not w_type.is_cpytype():
                _Py_Dealloc(space, obj)
            del state.py_objects_w2r[w_obj]
            # if the object was a container for borrowed references
            state.delete_borrower(w_obj)
    else:
        if not we_are_translated() and obj.c_ob_refcnt < 0:
            message = "Negative refcount for obj %s with type %s" % (
                obj, rffi.charp2str(obj.c_ob_type.c_tp_name))
            print >>sys.stderr, message
            assert False, message

@cpython_api([PyObject], lltype.Void)
def Py_IncRef(space, obj):
    if not obj:
        return
    obj.c_ob_refcnt += 1
    assert obj.c_ob_refcnt > 0
    if DEBUG_REFCOUNT:
        debug_refcount("INCREF", obj, obj.c_ob_refcnt, frame_stackdepth=3)

@cpython_api([PyObject], lltype.Void)
def _Py_NewReference(space, obj):
    obj.c_ob_refcnt = 1

def _Py_Dealloc(space, obj):
    from pypy.module.cpyext.api import generic_cpy_call_dont_decref
    pto = obj.c_ob_type
    #print >>sys.stderr, "Calling dealloc slot", pto.c_tp_dealloc, "of", obj, \
    #      "'s type which is", rffi.charp2str(pto.c_tp_name)
    generic_cpy_call_dont_decref(space, pto.c_tp_dealloc, obj)

#___________________________________________________________
# Support for borrowed references

def make_borrowed_ref(space, w_container, w_borrowed):
    """
    Create a borrowed reference, which will live as long as the container
    has a living reference (as a PyObject!)
    """
    if w_borrowed is None:
        return lltype.nullptr(PyObject.TO)

    state = space.fromcache(RefcountState)
    return state.make_borrowed(w_container, w_borrowed)

class BorrowPair:
    """
    Delays the creation of a borrowed reference.
    """
    def __init__(self, w_container, w_borrowed):
        self.w_container = w_container
        self.w_borrowed = w_borrowed

    def get_ref(self, space):
        return make_borrowed_ref(space, self.w_container, self.w_borrowed)

def borrow_from(container, borrowed):
    return BorrowPair(container, borrowed)

#___________________________________________________________

@cpython_api([rffi.VOIDP_real], lltype.Signed, error=CANNOT_FAIL)
def _Py_HashPointer(space, ptr):
    return rffi.cast(lltype.Signed, ptr)
