from pypy.interpreter.error import OperationError, operationerrfmt
from pypy.interpreter.baseobjspace import Wrappable
from pypy.interpreter.gateway import interp2app, unwrap_spec
from pypy.interpreter.typedef import TypeDef
from pypy.rpython.lltypesystem import lltype, rffi
from pypy.rlib.rarithmetic import intmask

from pypy.module._ffi_backend import cdataobj, misc


class W_CType(Wrappable):
    _immutable_ = True

    def __init__(self, space, name, size):
        self.space = space
        self.name = name
        self.size = size     # size of instances, or -1 if unknown

    def repr(self):
        space = self.space
        return space.wrap("<ctype '%s'>" % (self.name,))

    def cast(self, w_ob):
        raise NotImplementedError

    def int(self, cdata):
        space = self.space
        raise operationerrfmt(space.w_TypeError,
                              "int() not supported on cdata '%s'", self.name)

    def convert_to_object(self, cdata):
        raise NotImplementedError


class W_CTypePrimitive(W_CType):

    def cast(self, w_ob):
        space = self.space
        if cdataobj.check_cdata(space, w_ob):
            xxx
        elif space.isinstance_w(w_ob, space.w_str):
            xxx
        elif space.is_w(w_ob, space.w_None):
            value = 0
        else:
            value = misc.as_unsigned_long_long(space, w_ob, strict=False)
        w_cdata = cdataobj.W_CDataOwn(space, self.size, self)
        w_cdata.write_raw_integer_data(value)
        return w_cdata


class W_CTypePrimitiveChar(W_CTypePrimitive):

    def int(self, cdata):
        xxx


class W_CTypePrimitiveSigned(W_CTypePrimitive):

    def int(self, cdata):
        if self.value_fits_long:
            # this case is to handle enums, but also serves as a slight
            # performance improvement for some other primitive types
            value = intmask(misc.read_raw_signed_data(cdata, self.size))
            return self.space.wrap(value)
        else:
            return self.convert_to_object(cdata)

    def convert_to_object(self, cdata):
        value = misc.read_raw_signed_data(cdata, self.size)
        # xxx enum
        if self.value_fits_long:
            return self.space.wrap(intmask(value))
        else:
            return self.space.wrap(value)    # r_longlong => on 32-bit, 'long'


class W_CTypePrimitiveUnsigned(W_CTypePrimitive):

    def int(self, cdata):
        return self.convert_to_object(cdata)

    def convert_to_object(self, cdata):
        value = misc.read_raw_unsigned_data(cdata, self.size)
        if self.value_fits_long:
            return self.space.wrap(intmask(value))
        else:
            return self.space.wrap(value)    # r_ulonglong => 'long' object


W_CType.typedef = TypeDef(
    '_ffi_backend.CTypeDescr',
    __repr__ = interp2app(W_CType.repr),
    )
W_CType.acceptable_as_base_class = False


def check_ctype(space, w_obj):
    return space.is_w(space.type(w_obj), space.gettypefor(W_CType))
