# -*- coding: utf-8 -*-
"""
    objc_codegen
    ~~~~~~~

    Extension to ast that allow ast -> objective-c code generation. Based on "codegen", a tool for converting an ast to python, by Armin Ronacher.

    :copyright: Copyright 2008 by Armin Ronacher.
    :copyright: Copyright 2011 by Anders Hovmöller.
    :license: BSD.
"""
from ast import *
from _ast import Call
from mapping import BOOLOP_SYMBOLS, BINOP_SYMBOLS, UNARYOP_SYMBOLS, \
     CMPOP_SYMBOLS


def to_source(node, indent_with=' ' * 4, add_line_information=False):
    """This function can convert a node tree back into python sourcecode.
    This is useful for debugging purposes, especially if you're dealing with
    custom asts not generated by python itself.

    It could be that the sourcecode is evaluable when the AST itself is not
    compilable / evaluable.  The reason for this is that the AST contains some
    more data than regular sourcecode does, which is dropped during
    conversion.

    Each level of indentation is replaced with `indent_with`.  Per default this
    parameter is equal to four spaces as suggested by PEP 8, but it might be
    adjusted to match the application's styleguide.

    If `add_line_information` is set to `True` comments for the line numbers
    of the nodes are added to the output.  This can be used to spot wrong line
    number information of statement nodes.
    """
    generator = SourceGenerator(indent_with, add_line_information)
    generator.visit(node)
    lines = ''.join(generator.result).split('\n')
    for i in xrange(len(lines)):
        line = lines[i]
        if not line.strip() == '' and not line.strip().startswith('@') and not line.strip().endswith('}') and not line.strip().endswith('{'):
            lines[i] = line+';'
        if '__comment__ = @"' in line:
            lines[i] = line[:-1].replace('__comment__ = @"', '//')
    for key, attribs in generator.classAttributes.items():
        print '@interface %s {' % key
        for v in sorted(attribs):
            t = 'id'
            if v in generator.currentClassAttributeTypes:
                t = generator.currentClassAttributeTypes[v]
            print '%s%s %s;' % (indent_with, t, v)
        print '}'
        print '\n@end\n\n'
    return '\n'.join(lines)


# Utilities

def id_string(arg):
    if hasattr(arg, 'id'):
        id = arg.id
    elif hasattr(arg, 'elts'):
        ids = []
        for element in arg.elts:
            ids.append(element.id)
        id = "(%s)" % ", ".join(ids)
    else:
        id = str(arg)
    return id

def capitalize_first(s):
    if len(s) > 1:
        return s[0].capitalize() + s[1:]
    elif len(s) > 0:
        return s.capitalize()
    else:
        return s


class SourceGenerator(NodeVisitor):
    """This visitor is able to transform a well formed syntax tree into python
    sourcecode.  For more details have a look at the docstring of the
    `node_to_source` function.
    """

    def __init__(self, indent_with, add_line_information=False):
        self.result = []
        self._new = True
        self.indent_with = indent_with
        self.add_line_information = add_line_information
        self.indentation = 0
        self.new_lines = 0
        self.inClassDef = False
        self.currentClassAttributes = set()
        self.currentClassAttributeTypes = {}
        self.classAttributes = {}
        self.inMethodDef = False

    def write(self, x):
        assert(isinstance(x, str))
        if self.new_lines:
            if not self._new:
                self.result.append('\n' * self.new_lines)
            self.result.append(self.indent_with * self.indentation)
            self.new_lines = 0
        self.result.append(x)
        self._new = False

    def newline(self, node=None, extra=0):
        self.new_lines = max(self.new_lines, 1 + extra)
        if node is not None and self.add_line_information:
            self.write('# line: %s' % node.lineno)
            self.new_lines = 1

    def body(self, statements):
        self.new_line = True
        self.indentation += 1
        for stmt in statements:
            self.visit(stmt)
        if not statements:
            self.visit(Pass())
        self.indentation -= 1
        self.newline()
        self.write('}')

    def body_or_else(self, node):
        self.body(node.body)
        if node.orelse:
            self.newline()
            self.write('else {')
            self.body(node.orelse)

    def signature(self, node):
        want_comma = []
        def write_comma():
            if want_comma:
                self.write(', ')
            else:
                want_comma.append(True)

        padding = [None] * (len(node.args) - len(node.defaults))
        for arg, default in zip(node.args, padding + node.defaults):
            if self.inClassDef and arg.id == 'self':
                continue
            write_comma()
            self.write('id ')
            self.visit(arg)
            if default is not None:
                self.write('=')
                self.visit(default)
        if node.vararg is not None:
            write_comma()
            self.write('*' + node.vararg)
        if node.kwarg is not None:
            write_comma()
            self.write('**' + node.kwarg)

    def decorators(self, node):
        for decorator in node.decorator_list:
            self.newline(decorator)
            self.write('@')
            self.visit(decorator)


    # Statements

    def visit_Assign(self, node):
        if self.inClassDef and not self.inMethodDef:
            for target in node.targets:
                target_id = id_string(target)
                self.currentClassAttributes.add(target_id)
                if hasattr(node.value, 'func'):
                    self.currentClassAttributeTypes[target_id] = '%s id' % id_string(node.value.func)
                elif hasattr(node.value, 'elts'):
                    # this attribute is a list!
                    self.currentClassAttributeTypes[target_id] = 'NSArray *'
                elif hasattr(node.value, 'n'):
                    # this attribute is a number!
                    self.currentClassAttributeTypes[target_id] = repr(type(node.value.n)).split("'")[1]
                elif hasattr(node.value, 's'):
                    # this attribute is a string!
                    self.currentClassAttributeTypes[target_id] = 'NSString *'
                elif hasattr(node.value, 'id') and node.value.id in ('True', 'False'):
                    self.currentClassAttributeTypes[target_id] = 'BOOL'
                else:
                    print 'unknown member type:',node.value
                    print dir(node.value)
        else:
            self.newline(node)
            for idx, target in enumerate(node.targets):
                if idx:
                    self.write(', ')
                self.visit(target)
            self.write(' = ')
            self.visit(node.value)

    def visit_AugAssign(self, node):
        self.newline(node)
        self.visit(node.target)
        self.write(' '+BINOP_SYMBOLS[type(node.op)] + '= ')
        self.visit(node.value)

    def visit_ImportFrom(self, node):
        self.newline(node)
        self.write('// Python: from %s%s import ' % ('.' * node.level, node.module))
        for idx, item in enumerate(node.names):
            if idx:
                self.write(', ')
            self.visit(item)

    def visit_Import(self, node):
        self.newline(node)
        for item in node.names:
            self.write('// Python: import ')
            self.visit(item)

    def visit_Expr(self, node):
        self.newline(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.inMethodDef = True
        self.newline(extra=1)
        self.decorators(node)
        self.newline(node)
        if self.inClassDef:
            self.write('- (id)')

            node_name = node.name
            function_rename_map = {'__init__':'init', '__repr__':'description'}
            if node_name in function_rename_map:
                node_name = function_rename_map[node_name]

            remove_get_method_prefix = True

            #want_capitalization = False

            signature_items = node_name.split('_')

            # We want to keep underscore prefixes and suffixes
            prefix_count = 0
            for i in range(len(signature_items)):
                s = signature_items[i]
                if len(s) != 0:
                    prefix_count = i

            suffix_count = 0
            for i in xrange(len(signature_items)-1, -1, -1):
                s = signature_items[i]
                if len(s) != 0:
                    suffix_count = i

            # Filter out any empty entries
            signature_items = [s for s in signature_items if len(s) != 0]

            if len(signature_items) > 1:
                if remove_get_method_prefix and signature_items[0] == "get":
                    signature_items = signature_items[1:]
                if not remove_get_method_prefix or len(signature_items) > 1:
                    signature_items = [signature_items[0]] + [capitalize_first(s) for s in signature_items[1:]]

            # Add underscore prefixes and suffixes back in
            if prefix_count > 0:
                signature_items[0] = '_' * prefix_count + signature_items[0]

            if suffix_count > 0:
                signature_items[0] += '_' * suffix_count

            if node.args.args[0].id == "self":
                args_without_self = node.args.args[1:]
            else:
                args_without_self = node.args.args

            if len(args_without_self) > 0:
                decompose_function_name_into_signature = False

                if decompose_function_name_into_signature:
                    # assert(len(signature_items) == len(node.args.args))
                    decompose_function_name_into_signature_items = (len(signature_items) == len(args_without_self))

                if decompose_function_name_into_signature:
                    for sig, arg in zip(signature_items, args_without_self):
                        self.write(sig)
                        self.write(':(id)')
                        id = id_string(arg)
                        self.write(id)
                        self.write(' ')
                elif len(node.args.args) > 1:
                    node_name = ''.join(signature_items)
                    self.write(node_name)

                    if node_name == "init":
                        self.write("With")

                    capitalize_next = True

                    for arg in args_without_self:
                        arg_name = id_string(arg)
                        arg_sig = arg_name
                        if capitalize_next:
                            arg_sig = capitalize_first(arg_sig)
                            capitalize_next = False
                        self.write(arg_sig)
                        self.write(':(id)')
                        self.write(arg_name)
                        self.write(' ')
            else:
                self.write(node_name)
                self.write(' ')

            self.write('{')

            node.name = node_name
        else:
            self.write('id %s(' % node.name)
            self.signature(node.args)
            self.write(') {')
        self.body(node.body)
        self.inMethodDef = False

    def visit_ClassDef(self, node):
        self.inClassDef = True
        self.currentClassAttributes = set()
        have_args = []
        def paren_or_comma():
            if have_args:
                self.write(', ')
            else:
                have_args.append(True)
                self.write(' : ')
        self.newline(extra=2)
        self.decorators(node)
        self.newline(node)
        self.write('@implementation %s' % node.name)
        className = node.name
        for base in node.bases:
            paren_or_comma()
            self.visit(base)
        
        for stmt in node.body:
            self.visit(stmt)
        self.newline()
        self.write('\n@end')
        self.inClassDef = False
        self.classAttributes[className] = self.currentClassAttributes
        del self.currentClassAttributes

    def visit_If(self, node):
        self.newline(node)
        self.write('if (')
        self.visit(node.test)
        self.write(') {')
        self.body(node.body)
        while True:
            else_ = node.orelse
            if len(else_) == 1 and isinstance(else_[0], If):
                node = else_[0]
                self.newline()
                self.write('else if (')
                self.visit(node.test)
                self.write(') {')
                self.body(node.body)
            else:
                self.newline()
                self.write('else {')
                self.body(else_)
                break

    def visit_For(self, node):
        self.newline(node)
        self.write('for ')
        self.visit(node.target)
        self.write(' in ')
        self.visit(node.iter)
        self.write(':')
        self.body_or_else(node)

    def visit_While(self, node):
        self.newline(node)
        self.write('while ')
        self.visit(node.test)
        self.write(':')
        self.body_or_else(node)

    def visit_With(self, node):
        self.newline(node)
        self.write('with ')
        self.visit(node.context_expr)
        if node.optional_vars is not None:
            self.write(' as ')
            self.visit(node.optional_vars)
        self.write(':')
        self.body(node.body)

    def visit_Pass(self, node):
        self.newline(node)

    def visit_Print(self, node):
        self.newline(node)
        self.write('print ')
        want_comma = False
        if node.dest is not None:
            self.write(' >> ')
            self.visit(node.dest)
            want_comma = True
        for value in node.values:
            if want_comma:
                self.write(', ')
            self.visit(value)
            want_comma = True
        if not node.nl:
            self.write(',')

    def visit_Delete(self, node):
        self.newline(node)
        self.write('del ')
        for idx, target in enumerate(node.targets):
            if idx:
                self.write(', ')
            self.visit(target)

    def visit_ExceptHandler(self, node):
        'Not sure why these are different classes, but in py2.7 this is needed'
        return self.visit_excepthandler(node)

    def visit_TryExcept(self, node):
        self.newline(node)
        self.write('@try {')
        self.body(node.body)
        self.newline()
        for handler in node.handlers:
            self.visit(handler)

    def visit_TryFinally(self, node):
        self.newline(node)
        self.write('@try {')
        self.body(node.body)
        self.write('}')
        self.newline(node)
        self.write('@finally {')
        self.body(node.finalbody)
        self.write('}')

    def visit_Global(self, node):
        self.newline(node)
        self.write('global ' + ', '.join(node.names))

    def visit_Nonlocal(self, node):
        self.newline(node)
        self.write('nonlocal ' + ', '.join(node.names))

    def visit_Return(self, node):
        self.newline(node)
        self.write('return')
        if node.value is not None:
            self.write(' ')
            self.visit(node.value)

    def visit_Break(self, node):
        self.newline(node)
        self.write('break')

    def visit_Continue(self, node):
        self.newline(node)
        self.write('continue')

    def visit_Raise(self, node):
        # XXX: Python 2.6 / 3.0 compatibility
        self.newline(node)
        self.write('raise')
        if hasattr(node, 'exc') and node.exc is not None:
            self.write(' ')
            self.visit(node.exc)
            if node.cause is not None:
                self.write(' from ')
                self.visit(node.cause)
        elif hasattr(node, 'type') and node.type is not None:
            self.visit(node.type)
            if node.inst is not None:
                self.write(', ')
                self.visit(node.inst)
            if node.tback is not None:
                self.write(', ')
                self.visit(node.tback)

    # Expressions

    def visit_Attribute(self, node):
        self.visit(node.value)
        if hasattr(node.value, 'id') and node.value.id == 'self':
            self.currentClassAttributes.add(node.attr)
        #print hasattr(node.value, 'func')
        #if hasattr(node.value, 'func'):# and node.func.value.is_method:
        if hasattr(node, 'is_method') and node.is_method:
            self.write(' ')
        else:
            self.write('.')
        self.write(node.attr)

    def visit_Call_class(self, node):
        method_name = node.func.attr
        self.write('[')
        self.visit(node.func.value)
        arg_names = method_name.split('_')
        if len(node.args) != 0:
            for name, arg in zip(arg_names, node.args):
                self.write(' %s:' % name)
                self.visit(arg)
        else:
            self.write(' '+method_name)
        self.write(']')

    def visit_Call(self, node):
        node.func.is_method = hasattr(node.func, 'value')
        want_comma = []
        def write_comma():
            if want_comma:
                self.write(', ')
            else:
                want_comma.append(True)

        if node.func.is_method:
            self.visit_Call_class(node)
            return
        else:    
            self.visit(node.func)
        self.write('(')
        for arg in node.args:
            write_comma()
            self.visit(arg)
        for keyword in node.keywords:
            write_comma()
            self.write(keyword.arg + '=')
            self.visit(keyword.value)
        if node.starargs is not None:
            write_comma()
            self.write('*')
            self.visit(node.starargs)
        if node.kwargs is not None:
            write_comma()
            self.write('**')
            self.visit(node.kwargs)
        self.write(')')

    def visit_Name(self, node):
        self.write(node.id)

    def visit_Str(self, node):
        self.write('@"%s"' % node.s.replace('\n', '\\n'))

    def visit_Bytes(self, node):
        self.write(repr(node.s))

    def visit_Num(self, node):
        self.write(repr(node.n))

    def visit_Tuple(self, node):
        self.write('(')
        idx = -1
        for idx, item in enumerate(node.elts):
            if idx:
                self.write(', ')
            self.visit(item)
        self.write(idx and ')' or ',)')

    def sequence_visit(left, right):
        def visit(self, node):
            self.write(left)
            for idx, item in enumerate(node.elts):
                if idx:
                    self.write(', ')
                self.visit(item)
            self.write(right)
        return visit

    visit_List = sequence_visit('[', ']')
    visit_Set = sequence_visit('{', '}')
    del sequence_visit

    def visit_Dict(self, node):
        self.write('{')
        for idx, (key, value) in enumerate(zip(node.keys, node.values)):
            if idx:
                self.write(', ')
            self.visit(key)
            self.write(': ')
            self.visit(value)
        self.write('}')

    def visit_BinOp(self, node):
        self.visit(node.left)
        self.write(' %s ' % BINOP_SYMBOLS[type(node.op)])
        self.visit(node.right)

    def visit_BoolOp(self, node):
        self.write('(')
        for idx, value in enumerate(node.values):
            if idx:
                self.write(' %s ' % BOOLOP_SYMBOLS[type(node.op)])
            self.visit(value)
        self.write(')')

    def visit_Compare(self, node):
        self.write('(')
        self.visit(node.left)
        for op, right in zip(node.ops, node.comparators):
            self.write(' %s ' % CMPOP_SYMBOLS[type(op)])
            self.visit(right)
        self.write(')')

    def visit_UnaryOp(self, node):
        self.write('(')
        op = UNARYOP_SYMBOLS[type(node.op)]
        self.write(op)
        if op == 'not':
            self.write(' ')
        self.visit(node.operand)
        self.write(')')

    def visit_Subscript(self, node):
        self.visit(node.value)
        self.write('[')
        self.visit(node.slice)
        self.write(']')

    def visit_Slice(self, node):
        if node.lower is not None:
            self.visit(node.lower)
        self.write(':')
        if node.upper is not None:
            self.visit(node.upper)
        if node.step is not None:
            self.write(':')
            if not (isinstance(node.step, Name) and node.step.id == 'None'):
                self.visit(node.step)

    def visit_ExtSlice(self, node):
        for idx, item in node.dims:
            if idx:
                self.write(', ')
            self.visit(item)

    def visit_Yield(self, node):
        self.write('yield ')
        self.visit(node.value)

    def visit_Lambda(self, node):
        self.write('lambda ')
        self.signature(node.args)
        self.write(': ')
        self.visit(node.body)

    def visit_Ellipsis(self, node):
        self.write('Ellipsis')

    def generator_visit(left, right):
        def visit(self, node):
            self.write(left)
            self.visit(node.elt)
            for comprehension in node.generators:
                self.visit(comprehension)
            self.write(right)
        return visit

    visit_ListComp = generator_visit('[', ']')
    visit_GeneratorExp = generator_visit('(', ')')
    visit_SetComp = generator_visit('{', '}')
    del generator_visit

    def visit_DictComp(self, node):
        self.write('{')
        self.visit(node.key)
        self.write(': ')
        self.visit(node.value)
        for comprehension in node.generators:
            self.visit(comprehension)
        self.write('}')

    def visit_IfExp(self, node):
        self.write('(')
        self.visit(node.test)
        self.write(' ? ')
        self.visit(node.body)
        self.write(' : ')
        self.visit(node.orelse)
        self.write(')')

    def visit_Starred(self, node):
        self.write('*')
        self.visit(node.value)

    def visit_Repr(self, node):
        self.write('`')
        self.visit(node.value)
        self.write('`')

    # Helper Nodes

    def visit_alias(self, node):
        self.write(node.name)
        if node.asname is not None:
            self.write(' as ' + node.asname)

    def visit_comprehension(self, node):
        self.write(' for ')
        self.visit(node.target)
        self.write(' in ')
        self.visit(node.iter)
        if node.ifs:
            for if_ in node.ifs:
                self.write(' if ')
                self.visit(if_)

    def visit_excepthandler(self, node):
        self.newline(node)
        self.write('@catch (')
        if node.type is not None:
            self.visit(node.type)
            self.write('* ')
            if node.name is not None:
                self.visit(node.name)
        else:
            self.write('id')
        self.write(') {')
        self.body(node.body)

if __name__ == '__main__':
    import ast
    import os
    import sys
    
    if len(sys.argv) != 2:
        print "Syntax: codegen_objc <input.py>"
        sys.exit(1)

    input_filename = sys.argv[1]
    pathname = os.getcwd() + "/" + input_filename

    # Pre-processing comments
    lines = []
    with open(pathname, 'r') as f:
        for line in f.readlines():
            if line.strip().startswith('#'):
                lines.append(line.replace('"', '\\"').replace('#', '__comment__ = "', 1)[:-1]+'"\n')
            else:
                lines.append(line)
    code = ''.join(lines)

    code2 = """
# comment
class A:
    c = []
    def __init__(self):
        self.a = 1
        self.b = 2
        not_member = 10
        self.foo_bar_(self.a, self.b)
        self.drawString_atX_y_('foo', 10, 20)
    def drawString_atX_y_(self, s, x, y):
        pass
class B(A):
    pass

def foo(a, b):
    if a == b:
        return a+b
    else:
        return a*b
foo(1, 2)
"""
    code3 = """
a = [x*2 for x in range(10)]
class FooCell(NSCell):
    def noArgsFunc(self):
        return 5
        
    def drawWithFrame_inView_(self, cellFrame, controlView):
        bp = NSBezierPath.bezierPathWithRect_(cellFrame)
        IntToNSColor(self.objectValue()).set()
        bp.fill()
        a.foo().bar()
        a.foo()
        a.foo_bar_(a.baz_(c), b)
        foo().baz_(c)
"""

    node = ast.parse(code)

    print to_source(node)