from pypy.jit.backend.arm.codebuilder import ARMv7Builder
from pypy.jit.backend.arm import registers as r
#from pypy.jit.backend.arm.regalloc import RegAlloc, ARMRegisterManager
from pypy.jit.metainterp.resoperation import rop
from pypy.rpython.lltypesystem import lltype
# XXX Move to llsupport
from pypy.jit.backend.x86.support import values_array


class AssemblerARM(object):

    def __init__(self, cpu, failargs_limit=1000):
        self.mc = ARMv7Builder()
        self.cpu = cpu
        self.fail_boxes_int = values_array(lltype.Signed, failargs_limit)

    def assemble_loop(self, inputargs, operations, looptoken):
        assert len(inputargs) == 1
        reg = 0
        self.gen_func_prolog()
        addr = self.fail_boxes_int.get_addr_for_num(0)
        self.gen_load_int(r.r3, addr)
        self.mc.LDR_ri(r.r2, r.r3)
        for op in operations:
            if op.getopnum() == rop.INT_ADD:
                self.mc.ADD_ri(r.r1, r.r2, op.getarg(1).getint())
            elif op.getopnum() == rop.FINISH:
                n = self.cpu.get_fail_descr_number(op.getdescr())
                self.mc.MOV_ri(r.r0, n)
                self.mc.STR_ri(r.r1, r.r3)
                self.gen_func_epilog()

    def gen_func_epilog(self):
        self.mc.LDM(r.sp, r.callee_restored_registers)

    def gen_func_prolog(self):
        self.mc.PUSH(r.callee_saved_registers)

    def gen_load_int(self, reg, value):
        self.mc.MOV_ri(reg, (value & 0xFF))

        for offset in range(8, 25, 8):
            self.mc.MOV_ri(r.ip, (value >> offset) & 0xFF)
            self.mc.ORR_rr(reg, reg, r.ip, offset)
