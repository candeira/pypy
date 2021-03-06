/* Copy-and-pasted from CPython */

/* This code implemented by Dag.Gruneau@elsa.preseco.comm.se */
/* Fast NonRecursiveMutex support by Yakov Markovitch, markovitch@iso.ru */
/* Eliminated some memory leaks, gsw@agere.com */

#include <windows.h>
#include <stdio.h>
#include <limits.h>
#include <process.h>


/*
 * Thread support.
 */
/* In rpython, this file is pulled in by thread.c */

typedef struct RPyOpaque_ThreadLock NRMUTEX, *PNRMUTEX;

typedef struct {
	void (*func)(void);
	long id;
	HANDLE done;
} callobj;

static long _pypythread_stacksize = 0;

static void
bootstrap(void *call)
{
	callobj *obj = (callobj*)call;
	/* copy callobj since other thread might free it before we're done */
	void (*func)(void) = obj->func;

	obj->id = GetCurrentThreadId();
	ReleaseSemaphore(obj->done, 1, NULL);
	func();
}

long RPyThreadStart(void (*func)(void))
{
	unsigned long rv;
	callobj obj;

	obj.id = -1;	/* guilty until proved innocent */
	obj.func = func;
	obj.done = CreateSemaphore(NULL, 0, 1, NULL);
	if (obj.done == NULL)
		return -1;

	rv = _beginthread(bootstrap, _pypythread_stacksize, &obj);
	if (rv == (unsigned long)-1) {
		/* I've seen errno == EAGAIN here, which means "there are
		 * too many threads".
		 */
		obj.id = -1;
	}
	else {
		/* wait for thread to initialize, so we can get its id */
		WaitForSingleObject(obj.done, INFINITE);
		assert(obj.id != -1);
	}
	CloseHandle((HANDLE)obj.done);
	return obj.id;
}

/************************************************************/

/* minimum/maximum thread stack sizes supported */
#define THREAD_MIN_STACKSIZE    0x8000      /* 32kB */
#define THREAD_MAX_STACKSIZE    0x10000000  /* 256MB */

long RPyThreadGetStackSize(void)
{
	return _pypythread_stacksize;
}

long RPyThreadSetStackSize(long newsize)
{
	if (newsize == 0) {    /* set to default */
		_pypythread_stacksize = 0;
		return 0;
	}

	/* check the range */
	if (newsize >= THREAD_MIN_STACKSIZE && newsize < THREAD_MAX_STACKSIZE) {
		_pypythread_stacksize = newsize;
		return 0;
	}
	return -1;
}

/************************************************************/


static
BOOL InitializeNonRecursiveMutex(PNRMUTEX mutex)
{
    mutex->sem = CreateSemaphore(NULL, 1, 1, NULL);
    return !!mutex->sem;
}

static
VOID DeleteNonRecursiveMutex(PNRMUTEX mutex)
{
    /* No in-use check */
    CloseHandle(mutex->sem);
    mutex->sem = NULL ; /* Just in case */
}

static
DWORD EnterNonRecursiveMutex(PNRMUTEX mutex, RPY_TIMEOUT_T milliseconds)
{
    DWORD res;

    if (milliseconds < 0)
        return WaitForSingleObject(mutex->sem, INFINITE);

    while (milliseconds >= (RPY_TIMEOUT_T)INFINITE) {
        res = WaitForSingleObject(mutex->sem, INFINITE - 1);
        if (res != WAIT_TIMEOUT)
            return res;
        milliseconds -= (RPY_TIMEOUT_T)(INFINITE - 1);
    }
    return WaitForSingleObject(mutex->sem, (DWORD)milliseconds);
}

static
BOOL LeaveNonRecursiveMutex(PNRMUTEX mutex)
{
    return ReleaseSemaphore(mutex->sem, 1, NULL);
}

/************************************************************/

void RPyThreadAfterFork(void)
{
}

int RPyThreadLockInit(struct RPyOpaque_ThreadLock *lock)
{
  return InitializeNonRecursiveMutex(lock);
}

void RPyOpaqueDealloc_ThreadLock(struct RPyOpaque_ThreadLock *lock)
{
    if (lock->sem != NULL)
	DeleteNonRecursiveMutex(lock);
}

/*
 * Return 1 on success if the lock was acquired
 *
 * and 0 if the lock was not acquired. This means a 0 is returned
 * if the lock has already been acquired by this thread!
 */
RPyLockStatus
RPyThreadAcquireLockTimed(struct RPyOpaque_ThreadLock *lock,
			  RPY_TIMEOUT_T microseconds, int intr_flag)
{
    /* Fow now, intr_flag does nothing on Windows, and lock acquires are
     * uninterruptible.  */
    RPyLockStatus success;
    RPY_TIMEOUT_T milliseconds;

    if (microseconds >= 0) {
        milliseconds = microseconds / 1000;
        if (microseconds % 1000 > 0)
            ++milliseconds;
    }

    if (lock && EnterNonRecursiveMutex(lock, milliseconds) == WAIT_OBJECT_0) {
        success = RPY_LOCK_ACQUIRED;
    }
    else {
        success = RPY_LOCK_FAILURE;
    }

    return success;
}

int RPyThreadAcquireLock(struct RPyOpaque_ThreadLock *lock, int waitflag)
{
    return RPyThreadAcquireLockTimed(lock, waitflag ? -1 : 0, /*intr_flag=*/0);
}

void RPyThreadReleaseLock(struct RPyOpaque_ThreadLock *lock)
{
	if (!LeaveNonRecursiveMutex(lock))
		/* XXX complain? */;
}

/************************************************************/
/* GIL code                                                 */
/************************************************************/

typedef HANDLE mutex2_t;   /* a semaphore, on Windows */

static void gil_fatal(const char *msg) {
    fprintf(stderr, "Fatal error in the GIL: %s\n", msg);
    abort();
}

static inline void mutex2_init(mutex2_t *mutex) {
    *mutex = CreateSemaphore(NULL, 1, 1, NULL);
    if (*mutex == NULL)
        gil_fatal("CreateSemaphore failed");
}

static inline void mutex2_lock(mutex2_t *mutex) {
    WaitForSingleObject(*mutex, INFINITE);
}

static inline void mutex2_unlock(mutex2_t *mutex) {
    ReleaseSemaphore(*mutex, 1, NULL);
}

static inline void mutex2_init_locked(mutex2_t *mutex) {
    mutex2_init(mutex);
    mutex2_lock(mutex);
}

static inline void mutex2_loop_start(mutex2_t *mutex) { }
static inline void mutex2_loop_stop(mutex2_t *mutex) { }

static inline int mutex2_lock_timeout(mutex2_t *mutex, double delay)
{
    DWORD result = WaitForSingleObject(*mutex, (DWORD)(delay * 1000.0 + 0.999));
    return (result != WAIT_TIMEOUT);
}

#define mutex1_t      mutex2_t
#define mutex1_init   mutex2_init
#define mutex1_lock   mutex2_lock
#define mutex1_unlock mutex2_unlock

#ifdef _M_IA64
/* On Itanium, use 'acquire' memory ordering semantics */
#define lock_test_and_set(ptr, value)  InterlockedExchangeAcquire(ptr, value)
#else
#define lock_test_and_set(ptr, value)  InterlockedExchange(ptr, value)
#endif
#define atomic_increment(ptr)          InterlockedIncrement(ptr)
#define atomic_decrement(ptr)          InterlockedDecrement(ptr)

#include "src/thread_gil.c"
