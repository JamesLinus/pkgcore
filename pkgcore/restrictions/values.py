# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
value restrictions

works hand in hand with L{pkgcore.restrictions.packages}, these
classes match against a value handed in, package restrictions pull the
attr from a package instance and hand it to their wrapped restriction
(which is a value restriction).
"""

from pkgcore.restrictions import restriction, boolean, packages
from pkgcore.util import demandload
demandload.demandload(globals(), 're pkgcore.util:lists')

# Backwards compatibility.
value_type = restriction.value_type


class base(restriction.base):
    """Base restriction matching object for values.

    Beware: do not check for instances of this to detect value
    restrictions! Use the C{type} attribute instead.
    """

    __slots__ = ()

    type = restriction.value_type

    def force_True(self, pkg, attr, val):
        return self.match(val)

    def force_False(self, pkg, attr, val):
        return not self.match(val)


class GetAttrRestriction(base, packages.PackageRestriction):

    """Restriction pulling an attribute and applying a child restriction."""

    __slots__ = ()

    # XXX this needs further thought.
    #
    # The api for force_{True,False} is a ValueRestriction gets called
    # with a package instance, the attribute name (string), and the
    # current attribute value. We cannot really provide a child
    # restriction with a sensible pkg and a sensible attribute name,
    # so we just punt and return True/False depending on the current
    # state without "forcing" anything (default implementation in
    # "base").


class VersionRestriction(base):
    """use this as base for version restrictions.

    Gives a clue to what the restriction does.
    """
    __slots__ = ()


class StrMatch(base):
    """Base string matching restriction.

    All derivatives must be __slot__ based classes.
    """
    __slots__ = ("flags",)


class StrRegex(StrMatch):

    """
    regex based matching
    """

    __slots__ = ("regex", "_matchfunc", "ismatch")

    __inst_caching__ = True

    def __init__(self, regex, case_sensitive=True, match=False, negate=False):

        """
        @param regex: regex pattern to match
        @param case_sensitive: should the match be case sensitive?
        @param match: should C{re.match} be used instead of C{re.search}?
        @keyword negate: should the match results be negated?
        """

        sf = object.__setattr__
        sf(self, "regex", regex)
        sf(self, "ismatch", match)
        sf(self, "negate", negate)
        flags = 0
        if not case_sensitive:
            flags = re.I
        sf(self, "flags", flags)
        compiled_re = re.compile(regex, flags)
        if match:
            sf(self, "_matchfunc", compiled_re.match)
        else:
            sf(self, "_matchfunc", compiled_re.search)

    def match(self, value):
        if not isinstance(value, basestring):
            # Be too clever for our own good --marienz
            if value is None:
                value = ''
            else:
                value = str(value)
        return (self._matchfunc(value) is not None) != self.negate

    def intersect(self, other):
        if self == other:
            return self
        return None

    def __eq__(self, other):
        return (self.regex == other.regex and
                self.negate == other.negate and
                self.flags == other.flags and
                self.ismatch == other.ismatch)

    def __hash__(self):
        return hash((self.regex, self.negate, self.flags, self.ismatch))

    def __repr__(self):
        result = [self.__class__.__name__, repr(self.regex)]
        if self.negate:
            result.append('negated')
        if self.ismatch:
            result.append('match')
        else:
            result.append('search')
        result.append('@%#8x' % (id(self),))
        return '<%s>' % (' '.join(result),)

    def __str__(self):
        if self.ismatch:
            result = 'match '
        else:
            result = 'search '
        result += self.regex
        if self.negate:
            return 'not ' + result
        return result


class StrExactMatch(StrMatch):

    """
    exact string comparison match
    """

    __slots__ = ("exact", "flags")

    __inst_caching__ = True

    def __init__(self, exact, case_sensitive=True, negate=False):

        """
        @param exact: exact string to match
        @param case_sensitive: should the match be case sensitive?
        @keyword negate: should the match results be negated?
        """

        sf = object.__setattr__
        sf(self, "negate", negate)
        if not case_sensitive:
            sf(self, "flags", re.I)
            sf(self, "exact", str(exact).lower())
        else:
            sf(self, "flags", 0)
            sf(self, "exact", str(exact))

    def match(self, value):
        if self.flags == re.I:
            return (self.exact == value.lower()) != self.negate
        else:
            return (self.exact == value) != self.negate

    def intersect(self, other):
        s1, s2 = self.exact, other.exact
        if other.flags and not self.flags:
            s1 = s1.lower()
        elif self.flags and not other.flags:
            s2 = s2.lower()
        if s1 == s2 and self.negate == other.negate:
            if other.flags:
                return other
            return self
        return None

    def __eq__(self, other):
        return (self.exact == other.exact and
                self.negate == other.negate and
                self.flags == other.flags)

    def __hash__(self):
        return hash((self.exact, self.negate, self.flags))

    def __repr__(self):
        if self.negate:
            string = '<%s %r negated @%#8x>'
        else:
            string = '<%s %r @%#8x>'
        return string % (self.__class__.__name__, self.exact, id(self))

    def __str__(self):
        if self.negate:
            return "!= "+self.exact
        return "== "+self.exact


class StrGlobMatch(StrMatch):

    """
    globbing matches; essentially startswith and endswith matches
    """

    __slots__ = ("glob", "prefix")

    __inst_caching__ = True

    def __init__(self, glob, case_sensitive=True, prefix=True, negate=False):

        """
        @param glob: string chunk that must be matched
        @param case_sensitive: should the match be case sensitive?
        @param prefix: should the glob be a prefix check for matching,
            or postfix matching
        @keyword negate: should the match results be negated?
        """

        sf = object.__setattr__
        sf(self, "negate", negate)
        if not case_sensitive:
            sf(self, "flags", re.I)
            sf(self, "glob", str(glob).lower())
        else:
            sf(self, "flags", 0)
            sf(self, "glob", str(glob))
        sf(self, "prefix", prefix)

    def match(self, value):
        value = str(value)
        if self.flags == re.I:
            value = value.lower()
        if self.prefix:
            f = value.startswith
        else:
            f = value.endswith
        return f(self.glob) ^ self.negate

    def intersect(self, other):
        if self.match(other.glob):
            if self.negate == other.negate:
                return other
        elif other.match(self.glob):
            if self.negate == other.negate:
                return self
        return None

    def __eq__(self, other):
        try:
            return (self.glob == other.glob and
                    self.negate == other.negate and
                    self.flags == other.flags and
                    self.prefix == other.prefix)
        except AttributeError:
            return False

    def __hash__(self):
        return hash((self.glob, self.negate, self.flags, self.prefix))

    def __repr__(self):
        if self.negate:
            string = '<%s %r negated @%#8x>'
        else:
            string = '<%s %r @%#8x>'
        return string % (self.__class__.__name__, self.glob, id(self))

    def __str__(self):
        s = ''
        if self.negate:
            s = 'not '
        if self.prefix:
            return "%s%s*" % (s, self.glob)
        return "%s*%s" % (s, self.glob)


def EqualityMatch(val, negate=False):
    """
    equality test wrapping L{ComparisonMatch}
    """
    return ComparisonMatch(cmp, val, [0], negate=negate)

def _mangle_cmp_val(val):
    if val < 0:
        return -1
    elif val > 0:
        return 1
    return 0


class ComparisonMatch(base):
    """Match if the comparison funcs return value is what's required."""

    _op_converter = {"=": (0,)}
    _rev_op_converter = {(0,): "="}

    for k, v in (("<", (-1,)), (">", (1,))):
        _op_converter[k] = v
        _op_converter[k+"="] = tuple(sorted(v + (0,)))
        _rev_op_converter[v] = k
        _rev_op_converter[tuple(sorted(v+(0,)))] = k+"="
    _op_converter["!="] = _op_converter["<>"] = (-1, 1)
    _rev_op_converter[(-1, 1)] = "!="
    del k, v

    __slots__ = ("data", "cmp_func", "matching_vals")

    @classmethod
    def convert_str_op(cls, op_str):
        return cls._op_converter[op_str]

    @classmethod
    def convert_op_str(cls, op):
        return cls._rev_op_converter[tuple(sorted(op))]

    def __init__(self, cmp_func, data, matching_vals, negate=False):

        """
        @param cmp_func: comparison function that compares data against what
            is passed in during match
        @param data: data to base comparison against
        @param matching_vals: sequence, composed of
            [-1 (less then), 0 (equal), and 1 (greater then)].
            If you specify [-1,0], you're saying
            "result must be less then or equal to".
        @param negate: should the results be negated?
        """
        
        sf = object.__setattr__
        sf(self, "cmp_func", cmp_func)
        sf(self, "negate", negate)
        
        if not isinstance(matching_vals, (tuple, list)):
            if isinstance(matching_vals, basestring):
                matching_vals = self.convert_str_op(matching_vals)
            elif isinstance(matching_vals, int):
                matching_vals = [matching_vals]
            else:
                raise TypeError("matching_vals must be a list/tuple")

        sf(self, "data", data)
        if negate:
            sf(self, "matching_vals", 
                tuple(set([-1, 0, 1]).difference(_mangle_cmp_val(x)
                    for x in matching_vals)))
        else:
            sf(self, "matching_vals",
                tuple(_mangle_cmp_val(x) for x in matching_vals))

    def match(self, actual_val):
        return _mangle_cmp_val(
            self.cmp_func(actual_val, self.data)) in self.matching_vals

    def __hash__(self):
        return hash((self.cmp_func, self.matching_vals, self.data))

    def __eq__(self, other):
        try:
            return (self.cmp_func == other.cmp_func and
                    self.matching_vals == other.matching_vals and
                    self.data == other.data)
        except AttributeError:
            return False

    def __repr__(self):
        return '<%s %s %r @%#8x>' % (
            self.__class__.__name__, self.convert_op_str(self.matching_vals),
            self.data, id(self))

    def __str__(self):
        return "%s %s" % (self.convert_op_str(self.matching_vals), self.data)


class ContainmentMatch(base):

    """used for an 'in' style operation, 'x86' in ['x86','~x86'] for example
    note that negation of this *does* not result in a true NAND when all is on.
    """

    __slots__ = ("vals", "all", "_hash")

    __inst_caching__ = True

    def __init__(self, *vals, **kwds):

        """
        @param vals: what values to look for during match
        @keyword all: must all vals be present, or just one for a match
            to succeed?
        @keyword negate: should the match results be negated?
        """

        sf = object.__setattr__
        sf(self, "all", bool(kwds.pop("all", False)))

        # note that we're discarding any specialized __getitem__ on vals here.
        # this isn't optimal, and should be special cased for known
        # types (lists/tuples fex)
        sf(self, "vals", frozenset(vals))
        sf(self, "negate", kwds.get("negate", False))
        sf(self, "_hash", hash((self.all, self.negate, self.vals)))

    def __hash__(self):
        return self._hash

    def match(self, val):
        if isinstance(val, basestring):
            for fval in self.vals:
                if fval in val:
                    return not self.negate
            return self.negate

        # this can, and should be optimized to do len checks- iterate
        # over the smaller of the two see above about special casing
        # bits. need the same protection here, on the offchance (as
        # contents sets do), the __getitem__ is non standard.
        try:
            if self.all:
                i = iter(val)
                return bool(self.vals.difference(i)) == self.negate
            for x in self.vals:
                if x in val:
                    return not self.negate
            return self.negate
        except TypeError:
            # other way around.  rely on contains.
            if self.all:
                for k in self.vals:
                    if k not in val:
                        return self.negate
                return not self.negate
            for k in self.vals:
                if k in val:
                    return not self.negate


    def force_False(self, pkg, attr, val):

        # "More than one statement on a single line"
        # pylint: disable-msg=C0321

        # XXX pretty much positive this isn't working.
        if isinstance(val, basestring):
            # unchangable
            return not self.match(val)

        if self.negate:
            if self.all:
                def filter(truths):
                    return False in truths
                def true(r, pvals):
                    return pkg.request_enable(attr, r)
                def false(r, pvals):
                    return pkg.request_disable(attr, r)

                truths = [x in val for x in self.vals]

                for x in boolean.iterative_quad_toggling(
                    pkg, None, list(self.vals), 0, len(self.vals), truths,
                    filter, desired_false=false, desired_true=true):
                    return True
            else:
                if pkg.request_disable(attr, *self.vals):
                    return True
            return False

        if not self.all:
            if pkg.request_disable(attr, *self.vals):
                return True
        else:
            l = len(self.vals)
            def filter(truths):		return truths.count(True) < l
            def true(r, pvals):		return pkg.request_enable(attr, r)
            def false(r, pvals):	return pkg.request_disable(attr, r)
            truths = [x in val for x in self.vals]
            for x in boolean.iterative_quad_toggling(
                pkg, None, list(self.vals), 0, l, truths, filter,
                desired_false=false, desired_true=true):
                return True
        return False


    def force_True(self, pkg, attr, val):

        # "More than one statement on a single line"
        # pylint: disable-msg=C0321

        # XXX pretty much positive this isn't working.

        if isinstance(val, basestring):
            # unchangable
            return self.match(val)

        if not self.negate:
            if not self.all:
                def filter(truths):
                    return True in truths
                def true(r, pvals):
                    return pkg.request_enable(attr, r)
                def false(r, pvals):
                    return pkg.request_disable(attr, r)

                truths = [x in val for x in self.vals]

                for x in boolean.iterative_quad_toggling(
                    pkg, None, list(self.vals), 0, len(self.vals), truths,
                    filter, desired_false=false, desired_true=true):
                    return True
            else:
                if pkg.request_enable(attr, *self.vals):
                    return True
            return False

        # negation
        if not self.all:
            if pkg.request_disable(attr, *self.vals):
                return True
        else:
            def filter(truths):		return True not in truths
            def true(r, pvals):		return pkg.request_enable(attr, r)
            def false(r, pvals):	return pkg.request_disable(attr, r)
            truths = [x in val for x in self.vals]
            for x in boolean.iterative_quad_toggling(
                pkg, None, list(self.vals), 0, len(self.vals), truths, filter,
                desired_false=false, desired_true=true):
                return True
        return False


    def __eq__(self, other):
        try:
            return self is other or (self.all == other.all and
                    self.negate == other.negate and
                    self.vals == other.vals)
        except AttributeError:
            return False

    def __repr__(self):
        if self.negate:
            string = '<%s %r all=%s negated @%#8x>'
        else:
            string = '<%s %r all=%s @%#8x>'
        return string % (
            self.__class__.__name__, tuple(self.vals), self.all, id(self))

    def __str__(self):
        if self.negate:
            s = "not contains [%s]"
        else:
            s = "contains [%s]"
        return s % ', '.join(map(str, self.vals))


class FlatteningRestriction(base):

    """Flatten the values passed in and apply the nested restriction."""

    __slots__ = ('dont_iter', 'restriction')

    def __init__(self, dont_iter, childrestriction, negate=False):
        """Initialize.

        @type  dont_iter: type or tuple of types
        @param dont_iter: type(s) not to flatten.
                          Passed to L{pkgcore.util.lists.iflatten_instance}.
        @type  childrestriction: restriction
        @param childrestriction: restriction applied to the flattened list.
        """
        object.__setattr__(self, "negate", negate)
        object.__setattr__(self, "dont_iter", dont_iter)
        object.__setattr__(self, "restriction", childrestriction)

    def match(self, val):
        return self.restriction.match(
            lists.iflatten_instance(val, self.dont_iter)) != self.negate

    def __str__(self):
        return 'flattening_restriction: dont_iter = %s, restriction = %s' % (
            self.dont_iter, self.restriction)

    def __repr__(self):
        return '<%s restriction=%r dont_iter=%r negate=%r @%#8x>' % (
            self.__class__.__name__,
            self.restriction, self.dont_iter, self.negate,
            id(self))


class FunctionRestriction(base):

    """Convenience class for creating special restrictions."""

    __slots__ = ('func',)

    def __init__(self, func, negate=False):
        """Initialize.

        C{func} is used as match function.

        It will usually be impossible for the backend to optimize this
        restriction. So even though you can implement an arbitrary
        restriction using this class you should only use it if it is
        very unlikely backend-specific optimizations will be possible.
        """
        object.__setattr__(self, 'negate', negate)
        object.__setattr__(self, 'func', func)

    def match(self, val):
        return self.func(val) != self.negate

    def __repr__(self):
        return '<%s func=%r negate=%r @%#8x>' % (
            self.__class__.__name__, self.func, self.negate, id(self))


class AnyMatch(restriction.AnyMatch):

    __slots__ = ()

    def __init__(self, childrestriction, negate=False):
        # Hack: skip calling base.__init__. Doing this would make
        # restriction.base.__init__ run twice.
        restriction.AnyMatch.__init__(
            self, childrestriction, restriction.value_type, negate=negate)

    def force_True(self, pkg, attr, val):
        return self.match(val)

    def force_False(self, pkg, attr, val):
        return not self.match(val)


# "Invalid name" (pylint uses the module const regexp, not the class regexp)
# pylint: disable-msg=C0103

AndRestriction = restriction.curry_node_type(boolean.AndRestriction,
                                             restriction.value_type)
OrRestriction = restriction.curry_node_type(boolean.OrRestriction,
                                            restriction.value_type)

AlwaysBool = restriction.curry_node_type(restriction.AlwaysBool,
                                         restriction.value_type)

AlwaysTrue = AlwaysBool(negate=True)
AlwaysFalse = AlwaysBool(negate=False)
