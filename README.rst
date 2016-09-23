============
Nameko query
============

`Nameko <https://nameko.readthedocs.io/en/stable/>`_ extension for support of running queries.

Queries supports multiple replies for a single query sent and will be returned as a list.


Examples
--------

.. code:: python

    from nameko_query.responder import query_responder
    class BlockedListener(object):
        name = "service"
        routing_prefix = "service"
        @query_responder
        def method(self, parameters, message):
            return "hello world"


.. code:: python

    from nameko_query.request import ClusterQueryProxy
    def query_request(service_name, method_name, parameters={}):
        with ClusterQueryProxy({"AMQP_URI": "amqp://guest:guest@localhost", timeout=0.05) as cluster_query:
            service = getattr(cluster_query, service_name)
            method = getattr(service, method_name)
            return method(parameters)
    print query_request("service", "method", parameters)
