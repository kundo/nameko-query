from nameko_query.responder import QueryResponder, QueryHandler
from kombu import Queue, Connection
from kombu.pools import producers
from unittest import TestCase
from mock import MagicMock, patch
from nameko.exceptions import MethodNotFound

class FirstListener(object):
    name = "someservice"
    routing_prefix = "someservice"

    def user(self, body, message):
        return "hello"

class ServiceContainer(object):
    service_name = "dummy_service_container"
    service_cls = FirstListener

    def __init__(self, config):
        self.config = config
        self.shared_extensions = {}

class QueryResponderTest(TestCase):
    def setUp(self):
        self.qr = QueryResponder({"AMQP_URI": ""}, MagicMock())

    @patch("nameko_query.responder.Connection", return_value=MagicMock(spec=Connection))
    @patch("nameko_query.responder.kombu.serialization.dumps", return_value=None)
    @patch("kombu.pools.ProducerPool.acquire", return_value=MagicMock())
    def test_send_response(self, mock_acquire, mock_serializer, mock_connection):
        self.qr.send_response("Response", None)
        self.assertEqual(mock_serializer.call_count, 1)
        self.assertEqual(mock_acquire.call_count, 1)

        with producers[mock_connection].acquire(block=True) as producer:
            print(producer.publish.call_args_list)
            self.assertEqual(producer.publish.called, 1)
            self.assertEqual(
                producer.publish.call_args[0],
                ({'result': 'Response', 'error': None},)
            )

class QueryConsumerTest(TestCase):
    def setUp(self):
        self.q = QueryHandler()
        self.q.method_name = "user"
        self.q.rpc_consumer.container = ServiceContainer({})

    @patch("nameko_query.responder.Queue", return_value=MagicMock(spec=Queue))
    def test_setup(self, mock_queue):
        self.q.rpc_consumer.setup()
        self.assertTrue(self.q.rpc_consumer._registered)
        self.assertIsInstance(self.q.rpc_consumer.queue, Queue)

    def test_get_provider_for_method(self):
        self.q.rpc_consumer.register_provider(self.q)

        method = self.q.rpc_consumer.get_provider_for_method("someservice.user")
        self.assertIsInstance(method, QueryHandler)

    def test_failing_to_get_provider(self):
        self.q.rpc_consumer.register_provider(self.q)

        with self.assertRaises(MethodNotFound):
            self.q.rpc_consumer.get_provider_for_method("someservice.unknown")
