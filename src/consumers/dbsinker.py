"""This type of consumer is for object sink data into database"""

import socket
import json
import src.params as params

from multiprocessing import Process
from kafka import KafkaConsumer
from kafka.coordinator.assignors.range import RangePartitionAssignor
from kafka.coordinator.assignors.roundrobin import RoundRobinPartitionAssignor
from kafka.structs import OffsetAndMetadata, TopicPartition
from src.cassandra.db_writer import DBWriter


class DBSinker(Process):

    def __init__(self,
                 value_topic,
                 verbose=False,
                 rr_distribute=False,
                 group_id="sinker",
                 group=None,
                 target=None,
                 name=None):
        """
        OBJECT DETECTION IN FRAMES --> Consuming encoded frame messages, detect faces and their encodings [PRE PROCESS],
        publish it to processed_frame_topic where these values are used for face matching with query faces.
        :param url_topic:
        :param obj_topic:
        :param topic_partitions: number of partitions processed_frame_topic topic has, for distributing messages among partitions
        :param verbose: print logs on stdout
        :param rr_distribute:  use round robin partitioner and assignor, should be set same as respective producers or consumers.
        :param group_id: kafka used to attribute topic partition
        :param group: group should always be None; it exists solely for compatibility with threading.
        :param target: Process Target
        :param name: Process name
        """

        super().__init__(group=group, target=target, name=name)

        self.iam = "{}-{}".format(socket.gethostname(), self.name)
        self.value_topic = value_topic

        self.verbose = verbose
        self.rr_distribute = rr_distribute
        self.group_id = group_id
        self.sinker = DBWriter()
        print("[INFO] I am ", self.iam)

    def run(self):
        """Consume raw frames, detects faces, finds their encoding [PRE PROCESS],
           predictions Published to processed_frame_topic fro face matching."""

        # Connect to kafka, Consume frame obj bytes deserialize to json
        partition_assignment_strategy = [RoundRobinPartitionAssignor] if self.rr_distribute else [
            RangePartitionAssignor,
            RoundRobinPartitionAssignor]

        value_consumer = KafkaConsumer(group_id=self.group_id, client_id=self.iam,
                                       bootstrap_servers=[params.KAFKA_BROKER],
                                       key_deserializer=lambda key: key.decode(),
                                       value_deserializer=lambda value: json.loads(value.decode()),
                                       partition_assignment_strategy=partition_assignment_strategy,
                                       auto_offset_reset="earliest")

        value_consumer.subscribe([self.value_topic])

        try:
            while True:
                if self.verbose:
                    print("[Librarian {}] WAITING FOR NEXT FRAMES..".format(self.iam))

                value_messages = value_consumer.poll(timeout_ms=10, max_records=10)

                for topic_partition, msgs in value_messages.items():
                    if self.verbose:
                        print("[Sinker done]")
                    for msg in msgs:
                        msginfo = msg.value
                        # msginfo = json.loads(msginfo)
                        if msginfo['valuable']:
                            self.sinker.insert_new_to_frame(msginfo)
                        tp = TopicPartition(msg.topic, msg.partition)
                        offsets = {tp: OffsetAndMetadata(msg.offset, None)}
                        value_consumer.commit(offsets=offsets)

        except KeyboardInterrupt as e:
            print(e)
            pass

        finally:
            print("Closing Stream")
            value_consumer.close()
