from scg.core import *


def glorot_normal(input_size, output_size, fun=None, shape=None):
    base = {
        'tanh': 6.,
        'sigmoid': 6.,
        'leaky_relu': 2.,
        'relu': 2.,
        'prelu': 2.,
        'softplus': 2.,
        None: 6.
    }

    stddev = np.sqrt(base[fun] / (input_size + output_size))

    if shape is None:
        shape = [input_size, output_size]
    A = tf.Variable(tf.truncated_normal_initializer(stddev=stddev)(shape))

    return A


def he_normal(input_size, output_size, fun=None, shape=None):
    base = {
        'tanh': 1.,
        'sigmoid': 1.,
        'leaky_relu': 2.,
        'relu': 2.,
        'prelu': 2.,
        'softplus': 2.,
        None: 1.
    }

    stddev = np.sqrt(base[fun] / input_size)

    if shape is None:
        shape = [input_size, output_size]

    A = tf.Variable(tf.truncated_normal_initializer(stddev=stddev)(shape))

    return A


def norm_init(init):
    def _init(*args, **kwargs):
        A = init(*args, **kwargs)
        g = tf.Variable(1.)
        return g * A / tf.sqrt(tf.reduce_sum(tf.square(A)))
    return _init


def prelu(x, p=0.):
    return tf.nn.relu(x) + p * tf.minimum(0., x)


def dispatch_function(x, fun, **kwargs):
    functions = {
        'tanh': tf.tanh,
        'sigmoid': tf.sigmoid,
        'relu': tf.nn.relu,
        'softplus': tf.nn.softplus,
        'prelu': prelu,
        None: tf.identity
    }
    return functions[fun](x, **kwargs)


class Affine(NodePrototype):
    def __init__(self, input_size, output_size, fun=None, init=glorot_normal, b=None):
        NodePrototype.__init__(self)

        self.input_size = input_size
        self.output_size = output_size
        self.fun = fun

        self.A = None
        if init is not None:
            self.A = init(input_size, output_size, fun=fun)

        if b is None:
            b = tf.Variable(tf.zeros((1, output_size)))
        self.b = b

        if fun == 'prelu':
            self.p = tf.Variable(tf.random_uniform((self.output_size,), minval=-0.01, maxval=0.01))

    def flow(self, A=None, b=None, p=None, input=None, affine_only=False):
        if A is None:
            A = self.A
        if b is None:
            b = self.b

        assert input is not None

        y = tf.matmul(input, A) + b
        if affine_only:
            return y

        args = {}
        if self.fun == 'prelu':
            args['p'] = p if p is not None else self.p

        return dispatch_function(y, self.fun, **args)

    @property
    def shape(self):
        return [self.output_size]

    @property
    def variables(self):
        return [self.A, self.b] + [self.p] if self.fun == 'prelu' else []


class Concat(NodePrototype):
    def __init__(self, index=1):
        NodePrototype.__init__(self)
        self.index = index

    def flow(self, **inputs):
        values = [value for value in inputs.itervalues()]
        return tf.concat(values, self.index)


def concat(inputs, index=1):
    input_dict = dict()
    for i in range(len(inputs)):
        input_dict['concat_' + str(i)] = inputs[i]
    return Concat(index)(**input_dict)


class Slice(NodePrototype):
    def __init__(self, start, size):
        NodePrototype.__init__(self)

        self.start = start
        self.size = size

    def flow(self, input=None):
        assert input is not None
        return tf.slice(input, [0, self.start], [-1, self.size])


def slice(input, start, size):
    return Slice(start, size)(input)


def apply(f, name=None, **inputs):
    class Apply(NodePrototype):
        def __init__(self):
            NodePrototype.__init__(self)

        def flow(self, **inputs):
            return f(**inputs)
    return Apply()(name=name, **inputs)


class Pack(NodePrototype):
    def __init__(self):
        NodePrototype.__init__(self)

    def flow(self, **inputs):
        return tf.stack([input for input in inputs.itervalues()])


def pack(*inputs):
    input_dict = dict()
    for i in range(len(inputs)):
        input_dict['pack_' + str(i)] = inputs[i]
    return Pack()(**input_dict)


class Constant(NodePrototype):
    def __init__(self, value, shape=None):
        NodePrototype.__init__(self)
        self.value = value
        self._shape = shape

    def flow(self, **inputs):
        assert len(inputs) == 0
        return self.value

    @property
    def shape(self):
        return self._shape


class BatchRepeat(NodePrototype):
    def __init__(self, batch=None):
        NodePrototype.__init__(self)
        self.batch = batch

    def flow(self, input=None, batch=None):
        assert input is not None
        if batch is None:
            batch = self.batch
        input = tf.expand_dims(input, 0)
        shape = tf.unstack(tf.shape(input))
        shape[0] = batch
        for i in range(1, len(shape)):
            shape[i] = 1
        return tf.tile(input, tf.stack(shape))


def split(node, num_splits):
    class Split(NodePrototype):
        def __init__(self):
            NodePrototype.__init__(self)

        def flow(self, input=None):
            assert input is not None


class Reshape(NodePrototype):
    def __init__(self, shape):
        NodePrototype.__init__(self)
        self.shape = shape

    def flow(self, input=None):
        assert input is not None
        sh = tf.shape(input)
        return tf.reshape(input, tf.stack([sh[0]] + self.shape))


class Add(NodePrototype):
    def __init__(self, mul=1., input_shape=None):
        NodePrototype.__init__(self)
        self.mul = mul
        self.input_shape = input_shape

    def flow(self, a=None, b=None):
        assert a is not None
        assert b is not None
        return a + b * self.mul

    @property
    def shape(self):
        return self.input_shape


def add(a, b, mul=1.):
    return Add(mul=mul, input_shape=a.shape)(a=a, b=b)


class Multiply(NodePrototype):
    def __init__(self):
        NodePrototype.__init__(self)

    def flow(self, a=None, b=None):
        assert a is not None
        assert b is not None
        return a * b


def multiply(a, b):
    return Multiply()(a=a, b=b)


class DictExtractor(NodePrototype):
    def __init__(self, key):
        NodePrototype.__init__(self)
        self.key = key

    def flow(self, input=None):
        assert input is not None
        return input[self.key]


def by_key(input, key):
    return DictExtractor(key)(input=input)


def batch_repeat(input, donor):
    return BatchRepeat()(input=input, batch=StealBatch()(input=donor))


class Nonlinearity(NodePrototype):
    def __init__(self, fun='prelu', input_shape=None):
        NodePrototype.__init__(self)

        self.args = {}
        self.fun = fun
        self.input_shape = input_shape
        if self.fun == 'prelu':
            self.args['p'] = tf.Variable(tf.random_uniform((input_shape[-1],), minval=-0.01, maxval=0.01))

    def flow(self, input=None):
        assert input is not None

        input = NodePrototype.reshape(input, self.shape)
        output = dispatch_function(input, self.fun, **self.args)
        return NodePrototype.flatten(output)

    @property
    def shape(self):
        return self.input_shape

