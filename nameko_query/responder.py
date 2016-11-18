import logging
import sys
from functools import partial

import kombu
from kombu import Connection, Exchange, Queue
from kombu.pools import producers
from nameko.constants import AMQP_URI_CONFIG_KEY, DEFAULT_RETRY_POLICY, DEFAULT_SERIALIZER, SERIALIZER_CONFIG_KEY
from nameko.exceptions import ContainerBeingKilled, MethodNotFound, UnserializableValueError, serialize
from nameko.rpc import Rpc, RpcConsumer

logger = logging.getLogger(__name__)

QUERY_QUEUE_TEMPLATE = "query-{}"
QUERY_EXCHANGE = "nameko-query"
DEFAULT_EXCHANGE = ""

class QueryResponder(object):
    def __init__(self, config, message):
        self.config = config
        self.message = message

    def send_response(self, result, exc_info, **kwargs):
        error = None
        if exc_info is not None:
            error = serialize(exc_info[1])
            logger.warning("Sending error response %s", error)

        serializer = self.config.get(SERIALIZER_CONFIG_KEY, DEFAULT_SERIALIZER)

        try:
            kombu.serialization.dumps(result, serializer)
        except Exception:
            exc_info = sys.exc_info()
            error = serialize(UnserializableValueError(result))
            result = None

        conn = Connection(self.config[AMQP_URI_CONFIG_KEY])

        exchange = DEFAULT_EXCHANGE

        retry = kwargs.pop('retry', True)
        retry_policy = kwargs.pop('retry_policy', DEFAULT_RETRY_POLICY)

        with producers[conn].acquire(block=True) as producer:
            routing_key = self.message.properties['reply_to']
            correlation_id = self.message.properties.get('correlation_id')

            msg = {'result': result, 'error': error}

            logger.info("Sending message to %s %s: %s", exchange, routing_key, msg)

            producer.publish(
                msg, retry=retry, retry_policy=retry_policy,
                exchange=exchange, routing_key=routing_key,
                serializer=serializer,
                correlation_id=correlation_id, **kwargs)

        return result, exc_info

class QueryConsumer(RpcConsumer):
    def setup(self):
        if self.queue is None:
            service_name = self.container.service_name
            queue_name = QUERY_QUEUE_TEMPLATE.format(service_name)
            routing_key = '{}.*'.format(self.container.service_cls.routing_prefix)

            exchange = Exchange(QUERY_EXCHANGE, durable=True, type="topic")

            self.queue = Queue(
                queue_name,
                exchange=exchange,
                routing_key=routing_key,
                durable=True)

            self.queue_consumer.register_provider(self)
            self._registered = True

    def get_provider_for_method(self, routing_key):
        routing_prefix = self.container.service_cls.routing_prefix

        for provider in self._providers:
            key = '{}.{}'.format(routing_prefix, provider.method_name)
            if key == routing_key:
                return provider
        else:
            method_name = routing_key.split(".")[-1]
            logger.warning("Received message for unknown method: %s", method_name)
            raise MethodNotFound(method_name)

    def handle_result(self, message, result, exc_info):
        responder = QueryResponder(self.container.config, message)
        result, exc_info = responder.send_response(result, exc_info)

        self.queue_consumer.ack_message(message)
        return result, exc_info

class QueryHandler(Rpc):
    rpc_consumer = QueryConsumer()

    def handle_message(self, body, message):
        worker_ctx_cls = self.container.worker_ctx_cls
        context_data = self.unpack_message_headers(worker_ctx_cls, message)

        parameters = body.get("parameters")

        handle_result = partial(self.handle_result, message)
        try:
            self.container.spawn_worker(self, (parameters, message), {},
                                        context_data=context_data,
                                        handle_result=handle_result)
        except ContainerBeingKilled:
            self.rpc_consumer.requeue_message(message)

query_responder = QueryHandler.decorator
