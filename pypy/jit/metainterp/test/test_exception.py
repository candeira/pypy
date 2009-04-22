import py
from pypy.jit.metainterp.test.test_basic import LLJitMixin, OOJitMixin
from pypy.rlib.jit import JitDriver
from pypy.rlib.rarithmetic import ovfcheck
from pypy.jit.metainterp.policy import StopAtXPolicy


class ExceptionTests:

    def test_simple(self):
        def g(n):
            if n <= 0:
                raise MyError(n)
            return n - 1
        def f(n):
            try:
                return g(n)
            except MyError, e:
                return e.n + 10
        res = self.interp_operations(f, [9])
        assert res == 8
        res = self.interp_operations(f, [-99])
        assert res == -89

    def test_no_exception(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        class X:
            pass
        def f(n):
            while n > 0:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                X()
                n -= 1
            return n
        res = self.meta_interp(f, [10])
        assert res == 0
        if self.type_system == 'ootype':
            py.test.skip('need optimize.py')
        self.check_loops({'jump': 1,
                          'int_gt': 1, 'guard_true': 1,
                          'int_sub': 1})


    def test_bridge_from_guard_exception(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def check(n):
            if n % 2:
                raise ValueError
        
        def f(n):
            while n > 0:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                try:
                    check(n)
                    n -= 1
                except ValueError:
                    n -= 3
            return n

        res = self.meta_interp(f, [20], policy=StopAtXPolicy(check))
        assert res == f(20)

    def test_bridge_from_guard_no_exception(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def check(n):
            if n % 2 == 0:
                raise ValueError
        
        def f(n):
            while n > 0:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                try:
                    check(n)
                    n -= 1
                except ValueError:
                    n -= 3
            return n

        res = self.meta_interp(f, [20], policy=StopAtXPolicy(check))
        assert res == f(20)

    def test_loop(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def check(n):
            if n < 0:
                raise IndexError
        def f(n):
            try:
                while True:
                    myjitdriver.can_enter_jit(n=n)
                    myjitdriver.jit_merge_point(n=n)
                    check(n)
                    n = n - 10
            except IndexError:
                return n
        res = self.meta_interp(f, [54])
        assert res == -6

    def test_four_levels_checks(self):
        def d(n):
            if n < 0:
                raise MyError(n * 10)
        def c(n):
            d(n)
        def b(n):
            try:
                c(n)
            except IndexError:
                pass
        def a(n):
            try:
                b(n)
                return 0
            except MyError, e:
                return e.n
        def f(n):
            return a(n)
        
        res = self.interp_operations(f, [-4])
        assert res == -40

    def test_exception_from_outside(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def check(n):
            if n > -100:
                raise MyError(n)
        def f(n):
            while n > 0:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                try:
                    check(n)
                except MyError, e:
                    n = e.n - 5
            return n
        assert f(53) == -2
        res = self.meta_interp(f, [53], policy=StopAtXPolicy(check))
        assert res == -2

    def test_exception_from_outside_2(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def check(n):
            if n > -100:
                raise IndexError
        def g(n):
            check(n)
        def f(n):
            while n > 0:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                try:
                    g(n)
                except IndexError:
                    n = n - 5
            return n
        res = self.meta_interp(f, [53], policy=StopAtXPolicy(check))
        assert res == -2

    def test_exception_two_cases(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        class Error1(Exception): pass
        class Error2(Exception): pass
        class Error3(Exception): pass
        class Error4(Exception): pass
        def check(n):
            if n > 0:
                raise Error3
            else:
                raise Error2
        def f(n):
            while True:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                try:
                    check(n)
                except Error1:
                    pass
                except Error2:
                    break
                except Error3:
                    n = n - 5
                except Error4:
                    pass
            return n
        res = self.meta_interp(f, [53], policy=StopAtXPolicy(check))
        assert res == -2

    def test_exception_two_cases_2(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        class Error1(Exception): pass
        class Error2(Exception): pass
        class Error3(Exception): pass
        class Error4(Exception): pass
        def check(n):
            if n > 0:
                raise Error3
            else:
                raise Error2
        def g(n):
            check(n)
        def f(n):
            while True:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                try:
                    g(n)
                except Error1:
                    pass
                except Error2:
                    break
                except Error3:
                    n = n - 5
                except Error4:
                    pass
            return n
        res = self.meta_interp(f, [53], policy=StopAtXPolicy(check))
        assert res == -2

    def test_exception_later(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def check(n):
            if n < 0:
                raise MyError(n)
            return 5
        def f(n):
            try:
                while True:
                    myjitdriver.can_enter_jit(n=n)
                    myjitdriver.jit_merge_point(n=n)
                    n = n - check(n)
            except MyError, e:
                return e.n
        assert f(53) == -2
        res = self.meta_interp(f, [53], policy=StopAtXPolicy(check))
        assert res == -2

    def test_exception_and_then_no_exception(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def check(n):
            if n > 0:
                raise ValueError
            return n + 100
        def f(n):
            while True:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                try:
                    n = check(n)
                    break
                except ValueError:
                    n = n - 5
            return n
        assert f(53) == 98
        res = self.meta_interp(f, [53], policy=StopAtXPolicy(check))
        assert res == 98

    def test_raise(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def f(n):
            while True:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                if n < 0:
                    raise ValueError
                n = n - 1
        def main(n):
            try:
                f(n)
            except ValueError:
                return 132
        res = self.meta_interp(main, [13])
        assert res == 132

    def test_raise_through(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def check(n):
            if n < 0:
                raise ValueError
            return 1
        def f(n):
            while True:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                n -= check(n)
        def main(n):
            try:
                f(n)
            except ValueError:
                return 132
        res = self.meta_interp(main, [13], policy=StopAtXPolicy(check))
        assert res == 132

    def test_raise_through_wrong_exc(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def check(n):
            if n < 0:
                raise ValueError
            return 1
        def f(n):
            while True:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                try:
                    n -= check(n)
                except IndexError:
                    pass
        def main(n):
            try:
                f(n)
            except ValueError:
                return 132
        res = self.meta_interp(main, [13], policy=StopAtXPolicy(check))
        assert res == 132

    def test_raise_through_wrong_exc_2(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def check(n):
            if n < 0:
                raise ValueError
            else:
                raise IndexError
        def f(n):
            while True:
                myjitdriver.can_enter_jit(n=n)
                myjitdriver.jit_merge_point(n=n)
                try:
                    check(n)
                except IndexError:
                    n -= 1
        def main(n):
            try:
                f(n)
            except ValueError:
                return 132
        res = self.meta_interp(main, [13], policy=StopAtXPolicy(check))
        assert res == 132

    def test_int_ovf(self):
        myjitdriver = JitDriver(greens = [], reds = ['n'])
        def f(n):
            try:
                while 1:
                    myjitdriver.can_enter_jit(n=n)
                    myjitdriver.jit_merge_point(n=n)
                    n = ovfcheck(n * -3)
            except OverflowError:
                return n
        expected = f(1)
        res = self.meta_interp(f, [1])
        assert res == expected

    def test_int_mod_ovf_zer(self):
        def f(x, y):
            try:
                return ovfcheck(x%y)
            except ZeroDivisionError:
                return 1
            except OverflowError:
                return 2

        res = self.interp_operations(f, [1, 2])
        assert res == 1

    def test_int_lshift_ovf(self):
        from pypy.jit.metainterp.simple_optimize import Optimizer
        
        myjitdriver = JitDriver(greens = [], reds = ['n', 'x', 'y'])
        def f(x, y, n):
            while n < 100:
                myjitdriver.can_enter_jit(n=n, x=x, y=y)
                myjitdriver.jit_merge_point(n=n, x=x, y=y)
                y += 1
                try:
                    ovfcheck(x<<y)
                except OverflowError:
                    return 2
                n += 1
            return n

        res = self.meta_interp(f, [1, 1, 0], optimizer=Optimizer)
        assert res == f(1, 1, 0)

    def test_reraise_through_portal(self):
        jitdriver = JitDriver(greens = [], reds = ['n'])

        class SomeException(Exception):
            pass
        
        def portal(n):
            while n > 0:
                jitdriver.can_enter_jit(n=n)
                jitdriver.jit_merge_point(n=n)
                if n == 10:
                    raise SomeException
                n -= 1

        def f(n):
            try:
                portal(n)
            except SomeException, e:
                return 3
            return 2

        res = self.meta_interp(f, [100])
        assert res == 3

    def test_bridge_from_interpreter_exc(self):
        mydriver = JitDriver(reds = ['n'], greens = [])

        def f(n):
            while n > 0:
                mydriver.can_enter_jit(n=n)
                mydriver.jit_merge_point(n=n)
                n -= 2
            raise MyError(n)
        def main(n):
            try:
                f(n)
            except MyError, e:
                return e.n

        res = self.meta_interp(main, [41], repeat=7)
        assert res == -1
        self.check_tree_loop_count(2)      # the loop and the entry path
        # we get:
        #    ENTER             - compile the new loop
        #    ENTER (BlackHole) - leave
        #    ENTER             - compile the entry bridge
        #    ENTER             - compile the leaving path (raising MyError)
        self.check_enter_count(4)

class MyError(Exception):
    def __init__(self, n):
        self.n = n


class TestOOtype(ExceptionTests, OOJitMixin):
    pass

class TestLLtype(ExceptionTests, LLJitMixin):
    pass
