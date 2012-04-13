import py
from pypy.conftest import gettestobjspace


class AppTestTransaction: 
    def setup_class(cls):
        cls.space = gettestobjspace(usemodules=['transaction'])

    def test_set_num_threads(self):
        import transaction
        transaction.set_num_threads(4)

    def test_simple(self):
        import transaction
        lst = []
        transaction.add(lst.append, 5)
        transaction.add(lst.append, 6)
        transaction.add(lst.append, 7)
        transaction.run()
        assert sorted(lst) == [5, 6, 7]

    def test_almost_as_simple(self):
        import transaction
        lst = []
        def f(n):
            lst.append(n+0)
            lst.append(n+1)
            lst.append(n+2)
            lst.append(n+3)
            lst.append(n+4)
            lst.append(n+5)
            lst.append(n+6)
        transaction.add(f, 10)
        transaction.add(f, 20)
        transaction.add(f, 30)
        transaction.run()
        assert len(lst) == 7 * 3
        seen = set()
        for start in range(0, 21, 7):
            seen.add(lst[start])
            for index in range(7):
                assert lst[start + index] == lst[start] + index
        assert seen == set([10, 20, 30])

    def test_propagate_exception(self):
        import transaction, time
        lst = []
        def f(n):
            lst.append(n)
            time.sleep(0.5)
            raise ValueError(n)
        transaction.add(f, 10)
        transaction.add(f, 20)
        transaction.add(f, 30)
        try:
            transaction.run()
            assert 0, "should have raised ValueError"
        except ValueError, e:
            pass
        assert len(lst) == 1
        assert lst[0] == e.args[0]

    def test_clear_pending_transactions(self):
        import transaction
        class Foo(Exception):
            pass
        def raiseme():
            raise Foo
        for i in range(20):
            transaction.add(raiseme)
        try:
            transaction.run()
            assert 0, "should have raised Foo"
        except Foo:
            pass
        transaction.run()   # all the other 'raiseme's should have been cleared


class AppTestTransactionEmulator(AppTestTransaction):
    def setup_class(cls):
        # test for lib_pypy/transaction.py
        cls.space = gettestobjspace(usemodules=[])