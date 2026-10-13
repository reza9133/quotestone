"""Small GenLayer runtime simulator for local tests. It is a test aid, not the real GenVM.

It models the rules that matter for this contract:
  * storage is rolled back when a call fails and is read-only inside view methods;
  * storage, message context and block time are unreachable inside non-deterministic blocks;
  * web and model access exist only inside non-deterministic blocks;
  * every non-deterministic result must be calldata-encodable and is re-run by independent validator nodes;
  * public method arguments are type-checked against their annotations.
"""
import copy
import datetime
import inspect

__all__ = ["gl", "Address", "u256", "TreeMap", "ForbiddenInNondet", "ConsensusFailure", "RT"]


class ForbiddenInNondet(Exception):
    pass


class ConsensusFailure(Exception):
    pass


class UserError(Exception):
    def __init__(self, message=""):
        super().__init__(message)
        self.message = message


class VMError(Exception):
    pass


class Return:
    def __init__(self, calldata):
        self.calldata = calldata


class u256(int):
    def __new__(cls, value=0):
        value = int(value)
        if value < 0 or value >= 2 ** 256:
            raise OverflowError("u256 out of range")
        return super().__new__(cls, value)


class Address(str):
    def __str__(self):
        return "0x" + str.__str__(self)[2:].upper()


class Node:
    def __init__(self):
        self.pages = {}
        self.llm = None


class Response:
    def __init__(self, status, body):
        self.status, self.body, self.headers = status, body, {}


class Runtime:
    def __init__(self):
        self.reset()

    def reset(self):
        self.pages = {}
        self.llm = lambda prompt: {"verdict": "SUPPORTS", "challenge": "NONE", "reason": "ok"}
        self.nodes = [Node() for _ in range(5)]
        self.current = None
        self.in_nondet = 0
        self.readonly = 0
        self.sender = "0x" + "a1" * 20
        self.time = 1780000000
        self.time_format = None
        self.web_log = []
        self.prompts = []
        self.nondet_runs = 0

    def stamp(self):
        if self.time_format:
            return self.time_format(self.time)
        moment = datetime.datetime.fromtimestamp(self.time, datetime.timezone.utc)
        return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def forbid_in_nondet(self, what):
        if self.in_nondet:
            raise ForbiddenInNondet(what + " is not available inside a non-deterministic block")


RT = Runtime()


def _encode(value, path="result"):
    if value is None or isinstance(value, (bool, str, bytes, Address)):
        return value
    if isinstance(value, int):
        if abs(value) >= 2 ** 256:
            raise TypeError(path + ": integer out of calldata range")
        return int(value)
    if isinstance(value, list):
        return [_encode(v, path + "[]") for v in value]
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise TypeError(path + ": calldata maps need string keys")
        return {k: _encode(v, path + "." + k) for k, v in value.items()}
    raise TypeError(path + ": " + type(value).__name__ + " is not calldata-encodable")


class TreeMap:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self):
        self._data = {}

    def _read(self):
        RT.forbid_in_nondet("storage")

    def _write(self):
        RT.forbid_in_nondet("storage")
        if RT.readonly:
            raise RuntimeError("storage write inside a view method")

    def get(self, key, default=None):
        self._read()
        return self._data.get(key, default)

    def __getitem__(self, key):
        self._read()
        return self._data[key]

    def __setitem__(self, key, value):
        self._write()
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("this map stores str to str")
        self._data[key] = value

    def __delitem__(self, key):
        self._write()
        del self._data[key]

    def __contains__(self, key):
        self._read()
        return key in self._data

    def __iter__(self):
        self._read()
        return iter(sorted(self._data))

    def __len__(self):
        self._read()
        return len(self._data)


class _Field:
    def __init__(self, name, kind):
        self.name, self.kind = name, kind

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        RT.forbid_in_nondet("storage")
        store = obj.__dict__["_store"]
        if self.name not in store:
            store[self.name] = TreeMap() if self.kind is TreeMap else self.kind(0)
        return store[self.name]

    def __set__(self, obj, value):
        RT.forbid_in_nondet("storage")
        if RT.readonly:
            raise RuntimeError("storage write inside a view method")
        if self.kind is TreeMap:
            raise AttributeError("maps cannot be reassigned")
        if not isinstance(value, self.kind):
            raise TypeError(self.name + " expects " + self.kind.__name__ + ", got " + type(value).__name__)
        obj.__dict__["_store"][self.name] = value


class Contract:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, kind in cls.__dict__.get("__annotations__", {}).items():
            setattr(cls, name, _Field(name, kind))

    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls)
        obj.__dict__["_store"] = {}
        return obj


def _check_args(fn, args, kwargs):
    bound = inspect.signature(fn).bind(*args, **kwargs)
    kinds = {"int": int, "str": str, "bool": bool, "list": list, "dict": dict}
    for name, value in list(bound.arguments.items())[1:]:
        want = fn.__annotations__[name]
        if want is int and isinstance(value, bool):
            raise TypeError(name + " expects int")
        if not isinstance(value, kinds[want.__name__]):
            raise TypeError(name + " expects " + want.__name__ + ", got " + type(value).__name__)
        _encode(value, name)


def _public(readonly):
    def decorate(fn):
        hints = fn.__annotations__
        params = [p for p in inspect.signature(fn).parameters][1:]
        assert all(p in hints for p in params), fn.__name__ + ": every parameter needs an annotation"
        assert "return" in hints, fn.__name__ + ": missing return annotation"

        def wrapper(self, *args, **kwargs):
            if RT.in_nondet:
                raise ForbiddenInNondet("contract entry points are not callable inside a non-deterministic block")
            _check_args(fn, (self,) + args, kwargs)
            snapshot = copy.deepcopy(self.__dict__["_store"])
            RT.readonly += 1 if readonly else 0
            try:
                result = fn(self, *args, **kwargs)
                return _encode(result) if result is not None else None
            except BaseException:
                self.__dict__["_store"] = snapshot
                raise
            finally:
                RT.readonly -= 1 if readonly else 0

        wrapper.__name__ = fn.__name__
        wrapper.__wrapped__ = fn
        wrapper.is_view = readonly
        return wrapper
    return decorate


class _Public:
    write = staticmethod(_public(False))
    view = staticmethod(_public(True))


class _Web:
    def get(self, url, **kwargs):
        if not RT.in_nondet:
            raise RuntimeError("web access outside a non-deterministic block")
        RT.web_log.append((RT.in_nondet, url))
        node = RT.current
        entry = node.pages[url] if url in node.pages else RT.pages.get(url)
        if entry is None:
            raise ConnectionError("no route to " + url)
        if callable(entry):
            entry = entry()
        status, body = entry
        return Response(status, body)

    def render(self, url, **kwargs):
        raise NotImplementedError("rendering is not simulated; the contract must not rely on it")


class _Nondet:
    web = _Web()

    def exec_prompt(self, prompt, *, response_format="text", **kwargs):
        if not RT.in_nondet:
            raise RuntimeError("model access outside a non-deterministic block")
        RT.prompts.append(prompt)
        handler = RT.current.llm or RT.llm
        answer = handler(prompt)
        if isinstance(answer, Exception):
            raise answer
        if response_format == "json":
            if not isinstance(answer, dict):
                raise ValueError("model did not return a json object")
            return copy.deepcopy(answer)
        return str(answer)


def _run_nondet_unsafe(leader_fn, validator_fn):
    if RT.in_nondet:
        raise RuntimeError("non-deterministic blocks cannot nest")
    RT.nondet_runs += 1

    def run(index, fn, *args):
        RT.current, RT.in_nondet = RT.nodes[index], index + 1
        try:
            return fn(*args)
        finally:
            RT.current, RT.in_nondet = None, 0

    try:
        result = Return(_encode(run(0, leader_fn)))
    except UserError as error:
        result = error
    except ForbiddenInNondet:
        raise
    except Exception as error:
        result = VMError(str(error))
    for index in range(1, len(RT.nodes)):
        verdict = run(index, validator_fn, copy.deepcopy(result) if isinstance(result, Return) else result)
        if verdict is not True:
            raise ConsensusFailure("validator " + str(index) + " disagreed")
    if isinstance(result, Return):
        return copy.deepcopy(result.calldata)
    raise result


class _Vm:
    Return = Return
    UserError = UserError
    VMError = VMError
    run_nondet_unsafe = staticmethod(_run_nondet_unsafe)


class _Message:
    @property
    def sender_address(self):
        RT.forbid_in_nondet("message context")
        return Address(RT.sender)

    @property
    def value(self):
        RT.forbid_in_nondet("message context")
        return u256(0)


class _GL:
    Contract = Contract
    public = _Public()
    nondet = _Nondet()
    vm = _Vm()
    message = _Message()

    @property
    def message_raw(self):
        RT.forbid_in_nondet("message context")
        return {"datetime": RT.stamp()}


gl = _GL()
