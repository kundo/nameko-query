from kombu import Connection
from kombu.messaging import Consumer
from kombu.transport.pyamqp import Message
from mock import MagicMock, patch
from nameko_query.query_request import ClusterQueryProxy

from unittest import TestCase

def query_request(service_name, method_name, parameters={}):
    with ClusterQueryProxy({"AMQP_URI": ""}, timeout=0.05) as cluster_query:
        service = getattr(cluster_query, service_name)
        method = getattr(service, method_name)
        return method(parameters)

class MockQueryPollingQueueConsumer(object):
    consumer = MagicMock(spec=Consumer)

    def __init__(self, reply_msgs):
        self.reply_msgs = reply_msgs

    def get_message(self, correlation_id):
        reply = []
        for msg in self.reply_msgs:
            message = MagicMock(spec=Message)
            message.properties = {
                "correlation_id": correlation_id
            }
            reply.append(({"result": msg}, message))
        self.provider.handle_messages(reply)

    def register_provider(self, provider):
        self.provider = provider

    def unregister_provider(self, provider):
        self.provider = None

    def ack_message(self, message):
        pass

class QueryRequestTest(TestCase):
    @patch("nameko_query.query_request.QueryPollingQueueConsumer", return_value=MockQueryPollingQueueConsumer(["dummy"]))
    @patch("nameko_query.query_responder.Connection", return_value=MagicMock(spec=Connection))
    @patch("kombu.pools.ProducerPool.acquire", return_value=MagicMock())
    def test_running_query(self, mock_consumer, mock_acquire, mock_connection):
        responses = query_request("hello", "service")
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0], "dummy")

    @patch("nameko_query.query_request.QueryPollingQueueConsumer", return_value=MockQueryPollingQueueConsumer(["first", "second"]))
    @patch("nameko_query.query_responder.Connection", return_value=MagicMock(spec=Connection))
    @patch("kombu.pools.ProducerPool.acquire", return_value=MagicMock())
    def test_multiple_replies(self, mock_consumer, mock_acquire, mock_connection):
        responses = query_request("hello", "service")
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0], "first")
        self.assertEqual(responses[1], "second")
