from struct import pack, unpack_from
from socket import inet_ntoa, inet_aton, error as socket_error

from Tribler.dispersy.conversion import BinaryConversion
from Tribler.dispersy.message import DropPacket

ADDRESS_TYPE_IPV4 = 0x01
ADDRESS_TYPE_DOMAIN_NAME = 0x02


class TunnelConversion(BinaryConversion):
    def __init__(self, community):
        super(TunnelConversion, self).__init__(community, "\x02")

        self.define_meta_message(chr(1), community.get_meta_message(u"cell"), lambda message: self._encode_decode(self._encode_cell, self._decode_cell, message), self._decode_cell)
        self.define_meta_message(chr(2), community.get_meta_message(u"create"), lambda message: self._encode_decode(self._encode_create, self._decode_create, message), self._decode_create)
        self.define_meta_message(chr(3), community.get_meta_message(u"created"), lambda message: self._encode_decode(self._encode_created, self._decode_created, message), self._decode_created)
        self.define_meta_message(chr(4), community.get_meta_message(u"extend"), lambda message: self._encode_decode(self._encode_extend, self._decode_extend, message), self._decode_extend)
        self.define_meta_message(chr(5), community.get_meta_message(u"extended"), lambda message: self._encode_decode(self._encode_extended, self._decode_extended, message), self._decode_extended)
        self.define_meta_message(chr(6), community.get_meta_message(u"ping"), lambda message: self._encode_decode(self._encode_ping, self._decode_ping, message), self._decode_ping)
        self.define_meta_message(chr(7), community.get_meta_message(u"pong"), lambda message: self._encode_decode(self._encode_pong, self._decode_pong, message), self._decode_pong)
        self.define_meta_message(chr(8), community.get_meta_message(u"stats-request"), lambda message: self._encode_decode(self._encode_stats_request, self._decode_stats_request, message), self._decode_stats_request)
        self.define_meta_message(chr(9), community.get_meta_message(u"stats-response"), lambda message: self._encode_decode(self._encode_stats_response, self._decode_stats_response, message), self._decode_stats_response)

        self.define_meta_message(chr(10), community.get_meta_message(u"establish-intro"), lambda message: self._encode_decode(self._encode_establish_intro, self._decode_establish_intro, message), self._decode_establish_intro)
        self.define_meta_message(chr(11), community.get_meta_message(u"intro-established"), lambda message: self._encode_decode(self._encode_intro_established, self._decode_intro_established, message), self._decode_intro_established)
        self.define_meta_message(chr(12), community.get_meta_message(u"establish-rendezvous"), lambda message: self._encode_decode(self._encode_establish_rendezvous, self._decode_establish_rendezvous, message), self._decode_establish_rendezvous)
        self.define_meta_message(chr(13), community.get_meta_message(u"rendezvous-established"), lambda message: self._encode_decode(self._encode_rendezvous_established, self._decode_rendezvous_established, message), self._decode_rendezvous_established)
        self.define_meta_message(chr(14), community.get_meta_message(u"intro1"), lambda message: self._encode_decode(self._encode_intro1, self._decode_intro1, message), self._decode_intro1)
        self.define_meta_message(chr(15), community.get_meta_message(u"intro2"), lambda message: self._encode_decode(self._encode_intro2, self._decode_intro2, message), self._decode_intro2)
        self.define_meta_message(chr(16), community.get_meta_message(u"rendezvous1"), lambda message: self._encode_decode(self._encode_rendezvous1, self._decode_rendezvous1, message), self._decode_rendezvous1)
        self.define_meta_message(chr(17), community.get_meta_message(u"rendezvous2"), lambda message: self._encode_decode(self._encode_rendezvous2, self._decode_rendezvous2, message), self._decode_rendezvous2)

    def _encode_cell(self, message):
        payload = message.payload
        packet = pack("!IB", payload.circuit_id, self._encode_message_map[payload.message_type].byte) + payload.encrypted_message
        return packet,

    def _decode_cell(self, placeholder, offset, data):
        circuit_id, = unpack_from('!I', data, offset)
        offset += 4

        if not self._decode_message_map.has_key(data[offset]):
            raise DropPacket("Invalid message")
        message_type = self._decode_message_map[data[offset]].meta.name
        offset += 1

        encrypted_message = data[offset:]
        offset += len(encrypted_message)

        return offset, placeholder.meta.payload.implement(circuit_id, message_type, encrypted_message)

    def _encode_create(self, message):
        payload = message.payload
        packet = pack("!IH", payload.circuit_id, len(payload.key)) + payload.key
        return packet,

    def _decode_create(self, placeholder, offset, data):
        circuit_id, = unpack_from('!I', data, offset)
        offset += 4

        len_key, = unpack_from("!H", data, offset)
        offset += 2

        key = data[offset:offset + len_key]
        offset += len_key

        return offset, placeholder.meta.payload.implement(circuit_id, key)

    def _encode_created(self, message):
        payload = message.payload
        packet = pack("!IH", payload.circuit_id, len(payload.key)) + payload.key + payload.candidate_list
        return packet,

    def _decode_created(self, placeholder, offset, data):
        circuit_id, = unpack_from('!I', data, offset)
        offset += 4

        len_key, = unpack_from("!H", data, offset)
        offset += 2

        key = data[offset:offset + len_key]
        offset += len_key

        candidate_list = data[offset:]
        offset += len(candidate_list)

        return offset, placeholder.meta.payload.implement(circuit_id, key, candidate_list)

    def _encode_extend(self, message):
        payload = message.payload
        packet = pack("!IHH", payload.circuit_id, len(payload.extend_with), len(payload.key)) + payload.extend_with + payload.key
        return packet,

    def _decode_extend(self, placeholder, offset, data):
        circuit_id, = unpack_from('!I', data, offset)
        offset += 4

        len_extend_with, len_key = unpack_from("!HH", data, offset)
        offset += 4

        extend_with = data[offset:offset + len_extend_with]
        offset += len_extend_with

        key = data[offset:offset + len_key]
        offset += len_key

        return offset, placeholder.meta.payload.implement(circuit_id, key, extend_with)

    def _encode_extended(self, message):
        payload = message.payload
        return pack("!IH", payload.circuit_id, len(payload.key)) + payload.key + payload.candidate_list,

    def _decode_extended(self, placeholder, offset, data):
        circuit_id, = unpack_from('!I', data, offset)
        offset += 4

        key_length, = unpack_from("!H", data, offset)
        offset += 2

        key = data[offset:offset + key_length]
        offset += key_length

        candidate_list = data[offset:]
        offset += len(candidate_list)

        return offset, placeholder.meta.payload.implement(circuit_id, key, candidate_list)

    def _encode_ping(self, message):
        return pack('!IH', message.payload.circuit_id, message.payload.identifier),

    def _decode_ping(self, placeholder, offset, data):
        if len(data) < offset + 6:
            raise DropPacket("Insufficient packet size")

        circuit_id, identifier = unpack_from('!IH', data, offset)
        offset += 6

        return offset, placeholder.meta.payload.implement(circuit_id, identifier)

    def _encode_pong(self, message):
        return self._encode_ping(message)

    def _decode_pong(self, placeholder, offset, data):
        return self._decode_ping(placeholder, offset, data)

    def _encode_stats_request(self, message):
        return pack('!H', message.payload.identifier),

    def _decode_stats_request(self, placeholder, offset, data):
        identifier, = unpack_from('!H', data, offset)
        offset += 2

        return offset, placeholder.meta.payload.implement(identifier)

    def _encode_stats_response(self, message):
        stats_list = []
        for key in ['uptime', 'bytes_up', 'bytes_down', 'bytes_relay_up', 'bytes_relay_down', 'bytes_enter', 'bytes_exit']:
            stats_list.append(message.payload.stats.get(key, 0))

        return pack('!HIQQQQQQ', *([message.payload.identifier] + stats_list)),

    def _decode_stats_response(self, placeholder, offset, data):
        identifier, = unpack_from('!H', data, offset)
        offset += 2

        stats_list = unpack_from('!IQQQQQQ', data, offset)
        offset += 52
        stats_dict = dict(zip(['uptime', 'bytes_up', 'bytes_down', 'bytes_relay_up', 'bytes_relay_down', 'bytes_enter', 'bytes_exit'], stats_list))

        # Ignore the rest
        offset += len(data[offset:])

        return offset, placeholder.meta.payload.implement(identifier, stats_dict)

    def _encode_establish_intro(self, message):
        return pack('!IH20s', message.payload.circuit_id, message.payload.identifier, message.payload.service_key),

    def _decode_establish_intro(self, placeholder, offset, data):
        circuit_id, identifier, service_key = unpack_from('!IH20s', data, offset)
        offset += 26

        return offset, placeholder.meta.payload.implement(circuit_id, identifier, service_key)

    def _encode_intro_established(self, message):
        return pack('!IH', message.payload.circuit_id, message.payload.identifier),

    def _decode_intro_established(self, placeholder, offset, data):
        circuit_id, identifier = unpack_from('!IH', data, offset)
        offset += 6

        return offset, placeholder.meta.payload.implement(circuit_id, identifier)

    def _encode_establish_rendezvous(self, message):
        return pack('!IH20s', message.payload.circuit_id, message.payload.identifier, message.payload.cookie),

    def _decode_establish_rendezvous(self, placeholder, offset, data):
        circuit_id, identifier, cookie = unpack_from('!IH20s', data, offset)
        offset += 26

        return offset, placeholder.meta.payload.implement(circuit_id, identifier, cookie)

    def _encode_rendezvous_established(self, message):
        return pack('!IH', message.payload.circuit_id, message.payload.identifier),

    def _decode_rendezvous_established(self, placeholder, offset, data):
        circuit_id, identifier = unpack_from('!IH', data, offset)
        offset += 6

        return offset, placeholder.meta.payload.implement(circuit_id, identifier)

    def _encode_keys_request(self, message):
        return pack('!IH20s', message.payload.circuit_id, 
                    message.payload.identifier,
                    message.payload.service_key),

    def _decode_keys_request(self, placeholder, offset, data):
        circuit_id, identifier, service_key = unpack_from('!IH20s', data, offset)
        offset += 26
        return offset, placeholder.meta.payload.implement(circuit_id, identifier, service_key)

    def _encode_keys_response(self, message):
        return pack('!IH20s20s', message.payload.circuit_id, 
                    message.payload.identifier, 
                    message.payload.ip_key, 
                    message.payload.seeder_key),

    def _decode_keys_response(self, placeholder, offset, data):
        circuit_id, identifier, ip_key, seeder_key = unpack_from('!IH20s20s', data, offset)
        offset += 46
        return offset, placeholder.meta.payload.implement(circuit_id, identifier, ip_key, seeder_key)

    def _encode_intro1(self, message):
        return pack('!IH20s20s20s20s', 
                    message.payload.circuit_id, 
                    message.payload.identifier,
                    message.payload.key,
                    message.payload.cookie,
                    message.payload.rendezvous_point,
                    message.payload.service_key),

    def _decode_intro1(self, placeholder, offset, data):
        circuit_id, identifier, key, cookie, rp, service_key = unpack_from('!IH20s20s20s20s', data, offset)
        offset += 86
        return offset, placeholder.meta.payload.implement(circuit_id, identifier, key, 
                                                          cookie, rp, service_key)

    def _encode_intro2(self, message):
        return pack('!IH20s20s20s', 
                    message.payload.circuit_id, 
                    message.payload.identifier,
                    message.payload.key,
                    message.payload.cookie,
                    message.payload.rendezvous_point),

    def _decode_intro2(self, placeholder, offset, data):
        circuit_id, identifier, key, cookie, rendezvous_point = unpack_from('!IH20s20s20s', data, offset)
        offset += 66

        return offset, placeholder.meta.payload.implement(circuit_id, identifier, key, cookie, rendezvous_point)

    def _encode_rendezvous1(self, message):
        return pack('!IH20s20s', 
                    message.payload.circuit_id, 
                    message.payload.identifier,
                    message.payload.key,
                    message.payload.cookie),

    def _decode_rendezvous1(self, placeholder, offset, data):
        circuit_id, identifier, key, cookie = unpack_from('!IH20s20s', data, offset)
        offset += 46

        return offset, placeholder.meta.payload.implement(circuit_id, identifier, key, cookie)

    def _encode_rendezvous2(self, message):
        return pack('!IH20s', message.payload.circuit_id, message.payload.identifier, message.payload.key),

    def _decode_rendezvous2(self, placeholder, offset, data):
        circuit_id, identifier, key = unpack_from('!IH20s', data, offset)
        offset += 26

        return offset, placeholder.meta.payload.implement(circuit_id, identifier, key)

    def _encode_decode(self, encode, decode, message):
        result = encode(message)
        try:
            decode(None, 0, result[0])

        except DropPacket:
            from traceback import print_exc
            print_exc()
            raise
        except:
            pass
        return result

    @staticmethod
    def swap_circuit_id(packet, message_type, old_circuit_id, new_circuit_id):
        circuit_id_pos = 0 if message_type == u"data" else 31
        circuit_id, = unpack_from('!I', packet, circuit_id_pos)
        assert circuit_id == old_circuit_id, circuit_id
        packet = packet[:circuit_id_pos] + pack('!I', new_circuit_id) + packet[circuit_id_pos + 4:]
        return packet

    @staticmethod
    def get_circuit_id(packet, message_type):
        circuit_id_pos = 0 if message_type == u"data" else 31
        circuit_id, = unpack_from('!I', packet, circuit_id_pos)
        return circuit_id

    @staticmethod
    def split_encrypted_packet(packet, message_type):
        encryped_pos = 4 if message_type == u"data" else 36
        return packet[:encryped_pos], packet[encryped_pos:]

    @staticmethod
    def encode_data(circuit_id, dest_address, org_address, data):
        assert org_address

        def encode_address(host, port):
            try:
                ip = inet_aton(host)
                is_ip = True
            except socket_error:
                is_ip = False

            if is_ip:
                return pack("!B4sH", ADDRESS_TYPE_IPV4, ip, port)
            else:
                return pack("!BH", ADDRESS_TYPE_DOMAIN_NAME, len(host)) + host + pack("!H", port)

        return pack("!I", circuit_id) + encode_address(*dest_address) + encode_address(*org_address) + data

    @staticmethod
    def decode_data(packet):
        circuit_id, = unpack_from("!I", packet)
        offset = 4

        def decode_address(packet, offset):
            addr_type, = unpack_from("!B", packet, offset)
            offset += 1

            if addr_type == ADDRESS_TYPE_IPV4:
                host, port = unpack_from('!4sH', packet, offset)
                offset += 6
                return (inet_ntoa(host), port), offset

            elif addr_type == ADDRESS_TYPE_DOMAIN_NAME:
                length, = unpack_from('!H', packet, offset)
                offset += 2
                host = packet[offset:offset + length]
                offset += length
                port, = unpack_from('!H', packet, offset)
                offset += 2
                return (host, port), offset

            return None, offset

        dest_address, offset = decode_address(packet, offset)
        org_address, offset = decode_address(packet, offset)

        data = packet[offset:]

        return circuit_id, dest_address, org_address, data

    @staticmethod
    def convert_from_cell(packet):
        header = packet[:22] + packet[35] + packet[23:31]
        return header + packet[31:35] + packet[36:]

    @staticmethod
    def convert_to_cell(packet):
        header = packet[:22] + '\x01' + packet[23:31]
        return header + packet[31:35] + packet[22] + packet[35:]

    @staticmethod
    def could_be_utp(data):
        if len(data) < 20:
            return False
        byte1, byte2 = unpack_from('!BB', data)
        # Type should be 0..4, Ver should be 1
        if not (0 <= (byte1 >> 4) <= 4 and (byte1 & 15) == 1):
            return False
        # Extension should be 0..2
        if not (0 <= byte2 <= 2):
            return False
        return True

    @staticmethod
    def could_be_udp_trackers(data):
        # For the UDP tracker protocol the action field is either at position 0 or 8, and should be 0..3
        if len(data) >= 8 and (0 <= unpack_from('!I', data, 0)[0] <= 3) or \
           len(data) >= 12 and (0 <= unpack_from('!I', data, 8)[0] <= 3):
            return True
        return False
