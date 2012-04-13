import thread
from pypy.module.thread import ll_thread
from pypy.rlib.objectmodel import we_are_translated
from pypy.rpython.annlowlevel import llhelper
from pypy.rlib.debug import fatalerror


null_ll_lock = ll_thread.null_ll_lock

def allocate_lock():
    if we_are_translated():
        return ll_thread.allocate_ll_lock()
    else:
        return thread.allocate_lock()

def acquire(lock, wait):
    if we_are_translated():
        return ll_thread.acquire_NOAUTO(lock, wait)
    else:
        return lock.acquire(wait)

def release(lock):
    if we_are_translated():
        ll_thread.release_NOAUTO(lock)
    else:
        lock.release()

def start_new_thread(callback):
    if we_are_translated():
        llcallback = llhelper(ll_thread.CALLBACK, callback)
        ident = ll_thread.c_thread_start_NOGIL(llcallback)
        if ident == -1:
            fatalerror("cannot start thread")
    else:
        thread.start_new_thread(callback, ())