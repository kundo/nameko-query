import logging
import socket
import uuid

from kombu import Connection, Exchange, Queue
from kombu.pools import producers
from nameko.constants import AMQP_URI_CONFIG_KEY, DEFAULT_RETRY_POLICY, DEFAULT_SERIALIZER, SERIALIZER_CONFIG_KEY
from nameko.containers import WorkerContext
from nameko.rpc import MethodProxy, ReplyListener, ServiceProxy
from nameko.standalone.rpc import ClusterProxy, PollingQueueConsumer, SingleThreadedReplyListener, StandaloneProxyBase

from nameko_query.responder import DEFAULT_EXCHANGE, QUERY_EXCHANGE

logger = logging.getLogger(__name__)

class QueryPollingQueueConsumer(PollingQueueConsumer):
    def get_message(self, correlation_id):
        try:
            logger.debug("QueryPollingQueueConsumer waiting for messages")
            while True:
                self.consumer.channel.connection.client.drain_events(
                    timeout=self.timeout
                )

        except socket.timeout:
            logger.debug("QueryPollingQueueConsumer waited until timeout, returning messages")
            # Normal path, we wait for the timeout before returning anything
            replies = self.replies.pop(correlation_id, None)
            if replies:
                logger.debug("Retrived %s replies", len(replies))
                self.provider.handle_messages(replies)
                return

            # Send an empty response in case of no replies
            logger.debug("No replies retrived")
            event = self.provider._reply_events.pop(correlation_id)
            event.send([])

        except KeyboardInterrupt as exc:
            logger.debug("KeyboardInterrupt while waitng for replies")
            event = self.provider._reply_events.pop(correlation_id)
            event.send_exception(exc)
            # exception may have killed the connection
            self._setup_consumer()

    def on_message(self, body, message):
        msg_correlation_id = message.properties.get('correlation_id')
        if msg_correlation_id not in self.provider._reply_events:
            logger.debug("Unknown correlation id: %s", msg_correlation_id)
        if msg_correlation_id not in self.replies:
            self.replies[msg_correlation_id] = []
        logger.debug("Received message %s", body)
        self.replies[msg_correlation_id].append((body, message))

class QueryReplyListener(ReplyListener):
    def setup(self):
        service_uuid = uuid.uuid4()
        queue_name = str(service_uuid)
        self.routing_key = str(service_uuid)

        exchange = DEFAULT_EXCHANGE

        self.queue = Queue(
            queue_name,
            exchange=exchange,
            auto_delete=True,
            exclusive=True,
        )

        self.queue_consumer.register_provider(self)

    def handle_messages(self, replies):
        correlation_id = replies[0][1].properties.get('correlation_id')
        for body, message in replies:
            self.queue_consumer.ack_message(message)
            cid = message.properties.get('correlation_id')
            assert cid == correlation_id

        client_event = self._reply_events.pop(correlation_id, None)
        if client_event is not None:
            client_event.send(replies)
        else:
            logger.debug("Unknown correlation id: %s", correlation_id)

class QueryMethodProxy(MethodProxy):
    def _call(self, *args, **kwargs):
        logger.debug('Calling %s', self)

        worker_ctx = self.worker_ctx
        container = worker_ctx.container

        msg = {'parameters': args[0]}

        conn = Connection(
            container.config[AMQP_URI_CONFIG_KEY],
            transport_options={'confirm_publish': True},
        )

        serializer = container.config.get(
            SERIALIZER_CONFIG_KEY, DEFAULT_SERIALIZER)

        routing_key = '{}.{}'.format(self.service_name, self.method_name)

        exchange = Exchange(QUERY_EXCHANGE, durable=True, type="topic")

        with producers[conn].acquire(block=True) as producer:

            headers = self.get_message_headers(worker_ctx)
            correlation_id = str(uuid.uuid4())

            reply_listener = self.reply_listener
            reply_to_routing_key = reply_listener.routing_key
            reply_event = reply_listener.get_reply_event(correlation_id)

            logger.debug("Publishing message to %s %s: %s", exchange, routing_key, msg)
            producer.publish(
                msg,
                exchange=exchange,
                routing_key=routing_key,
                mandatory=True,
                serializer=serializer,
                reply_to=reply_to_routing_key,
                headers=headers,
                correlation_id=correlation_id,
                retry=True,
                retry_policy=DEFAULT_RETRY_POLICY
            )

        return QueryReply(reply_event)

class QueryServiceProxy(ServiceProxy):
    def __getattr__(self, name):
        return QueryMethodProxy(self.worker_ctx, self.service_name, name, self.reply_listener)

class QueryReply(object):
    resp_body = None

    def __init__(self, reply_event):
        self.reply_event = reply_event

    def result(self):
        logger.debug('Waiting for Query reply event %s', self)

        if self.resp_body is None:
            self.resp_body = self.reply_event.wait()
            logger.debug('Query reply event complete %s %s', self, self.resp_body)

        results = []
        for body, message in self.resp_body:
            error = body.get('error')
            result = body.get('result')
            if error:
                logger.error("Error in QueryReply %r", error)
            if result:
                results.append(result)

        return results

class QuerySingleThreadedReplyListener(SingleThreadedReplyListener, QueryReplyListener):
    def __init__(self, timeout=None):
        super(QuerySingleThreadedReplyListener, self).__init__()
        self.queue_consumer = QueryPollingQueueConsumer(timeout=timeout)

class ClusterQueryProxy(StandaloneProxyBase):
    class ServiceContainer(StandaloneProxyBase.ServiceContainer):
        service_name = "query-consumer"

    def __init__(
        self, config, context_data=None, timeout=None,
        worker_ctx_cls=WorkerContext
    ):
        container = self.ServiceContainer(config)

        reply_listener = QuerySingleThreadedReplyListener(timeout=timeout).bind(container)

        self._worker_ctx = worker_ctx_cls(
            container, service=None, entrypoint=self.Dummy,
            data=context_data)
        self._reply_listener = reply_listener
        self._proxy = QueryClusterProxy(self._worker_ctx, self._reply_listener)

class QueryClusterProxy(ClusterProxy):
    def __getattr__(self, name):
        if name not in self._proxies:
            self._proxies[name] = QueryServiceProxy(
                self._worker_ctx, name, self._reply_listener)
        return self._proxies[name]
