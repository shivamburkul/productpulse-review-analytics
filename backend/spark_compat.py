import pickle
import sys


def apply():
    """PySpark 3.5.x bundles an old cloudpickle that recurses forever on Python 3.14.
    Use the project-local cloudpickle>=3.1 package for serialising functions on the driver."""
    if sys.version_info < (3, 14):
        return "bundled cloudpickle"
    import cloudpickle
    from pyspark import serializers

    def dumps(self, obj):
        try:
            return cloudpickle.dumps(obj, serializers.pickle_protocol)
        except pickle.PickleError:
            raise
        except Exception as e:
            raise pickle.PicklingError("Could not serialize object: %s: %s" % (e.__class__.__name__, e))

    serializers.CloudPickleSerializer.dumps = dumps
    return "cloudpickle %s" % cloudpickle.__version__
