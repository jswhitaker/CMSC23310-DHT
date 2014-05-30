# node.py
import rt

import hashlib
import random
import json
import sys
import signal
import time
from datetime import datetime
import zmq
import keystore
from zmq.eventloop import ioloop, zmqstream
ioloop.install()

class Node(object):

    def __init__(self, name, pep, rep, spammer, peers):
        self.loop = ioloop.ZMQIOLoop.current()
        self.context = zmq.Context()
        print random.randint(0, 15)
        print random.randint(0, 15)
        # SUB socket for receiving messages from the broker
        self.sub_sock = self.context.socket(zmq.SUB)
        self.sub_sock.connect(pep)
        # make sure we get messages meant for us!
        self.sub_sock.set(zmq.SUBSCRIBE, name)
        self.sub = zmqstream.ZMQStream(self.sub_sock, self.loop)
        self.sub.on_recv(self.handle)

        # REQ socket for sending messages to the broker
        self.req_sock = self.context.socket(zmq.REQ)
        self.req_sock.connect(rep)
        self.req = zmqstream.ZMQStream(self.req_sock, self.loop)
        self.req.on_recv(self.handle_broker_message)

        self.name = name
        self.peers = peers
        self.spammer = spammer
        self.rt = rt.RoutingTable()
        self.ringPos = int(hashlib.sha1(name).hexdigest(), 16)
        self.keystore = keystore.KeyStore()
        self.pendingMessages = [] 

        for sig in [signal.SIGTERM, signal.SIGINT, signal.SIGHUP,
                    signal.SIGQUIT]:
            signal.signal(sig, self.shutdown)
        """
        print self.name, self.peers
        print time.time()
        dt = datetime.now()
        print dt.microsecond
        dt2 = datetime.now()
        print dt2.microsecond
        """
    def start(self):
        print self.name, self.peers, self.ringPos
        self.loop.start()


    def handle_broker_message(self, msg_frames):
        print "Handling broker message!"
        print "len is", len(msg_frames)
        print "name is", msg_frames[0]

        """Idea: hijack handling function to do heartbeat sweeping loop?
        as well as just simply sending them? Or is there another place to put that?"""
    def handle(self, msg_frames):
        print "Handling!"
        assert len(msg_frames) == 3
        assert msg_frames[0] == self.name
        # Second field is the empty delimiter
        msg = json.loads(msg_frames[2])

        if msg['type'] == 'get':
            print "node %d got get" % self.name

            k = msg['key']
            hashkey = int(hashlib.sha1(k).hexdigest(), 16)
          
            keyholder = self.rt.findSucc(hashkey)
            if  keyholder != self.ringPos: #If the keyholder is not me...
                """
                Ask the successor  for the value.
                Consult the routing table, and then send the
                message.
                """
                forwardMsg = msg
                forwardMsg['destination'] = keyholder 
                self.req.send_json(forwardMsg)
                """Does not yet take into account dead targets"""
            else:
                """
                  If we have the value, we can simply send it back.
                  We do need to make sure that it's in our space because it's
                  ours, and not because it's something we're just replicating.
                """
                entry = self.keystore.GetKey(k)
                if entry != None:
                    self.req.send_json({'type': 'getResponse', 'id' : msg['id'],
                                    'value' : v})
                else: 
                    """Send error"""
                    self.req.send_json({'type': 'getResponse', 'id' : msg['id'],
                                    'error' : "No match to key found!"})
            
            
        elif msg['type'] == 'set':
            # TODO: Handle the keystore stuff.
            k = msg['key']
            v = msg['value']
            hashKey = int(hashlib.sha1(k).hexdigest(), 16)
        

            keyholder = self.rt.findSucc(hashkey)
            if  keyholder != self.ringPos: #If the keyholder is not me...
                forwardMsg = msg
                forwardMsg['destination'] = keyholder 
                self.req.send_json(forwardMsg)
                """TODO: Make a sort of queue to monitor forwarded messages"""

            else: 
                """SET KEY"""
                KeyObj = KeyVal(, k, v, datetime.now())
                self.keystore.AddKey(KeyObj)
                self.req.send_json('type': 'setResponse', 'id': msg['id'], 'value': v)



        elif msg['type'] == 'hello':
            # Should be the very first message we see.
            self.req.send_json({'type': 'helloResponse', 'source': self.name})
            print "Got hello"
        
        elif msg['type'] == 'heartbeat':
            # TODO: We determine the source and update our routing table.
            src = msg['source']
            timestamp = msg['timestamp']
            print "Got a heartbeat from", src, "at", timestamp
            
            rtentry = rt.findRTEntry(src)
            if rtentry != None: 
                rtentry.updateTimestamp(timestamp) 
            else:
                self.rt.addRTEntry(src)

        elif msg['type'] == 'getResponse' or msg['type'] == 'setResponse':
            """this is presumable from a  node we forwarded a request to. send it back to the client"""
            newMsg = msg
            del newMsg['source']
            del newMsg['destination']
            self.req.send_json(newMsg)



        else:
            print "unrecognized message type ("%s") recieved by node %d" % (msg['type'], self.name) #TODO: to be filled out        

        
        """Let's put all "maintenance" actions here, as this is the best "loop" we have at the moment"""

        """Sweeping function to retire dead nodes"""
        self.rt.rtSweep(datetime.now())

        """send heartbeat to all peers"""
        for peer in self.peers:
            self.req.send_json('type': 'heartbeat', 'source': self.name, 'destination': peer, 'timestamp': datetime.now())


       self.SweepPendingMessages()



    """Checks to see if nodes we forwarded messages to have since died. 
       Reforwards messages to new Successors"""
    def SweepPendingMessages(self):
        pass

    # Message Handler, expects a message object, conversion will be done before this function
    # is called
    #TODO: I'm not really sure we need this anymore
    def MsgHandle(self, msg):
        mType = msg.getType()
        if mType == "hello":
            """
            Send a hello response back to the broker
            self.req.send_json
            """
        elif mType == "get":
            """
            If it belongs to us, return a getResponse or getError.
            Else, forward to correct node according to RT
            """
            pass

        elif mType == "set":
            """
            If key belongs to us, set key, send replica messages to 2 successors of our node, then send setResponse
            Else forward set msg to correct node according to RT
            """
            pass

        elif mType == "replicate":
            """
            Update keystore based on values sent in
            """
            pass

        elif mType == "merge":
            """
            We are taking over a section of some one elses keyspace, compare our keyvals with the 
            ones sent to us, latest timestamp wins
            Send full keystore replicate message to succsors
            """
            pass

        elif mType == "heartbeat":
            """
            Used to update timeouts on RT, also contains message digests of all messages recieved since last
            heartbeat was sent. These digests allow for other nodes to clear their queue of messages
            that they are awaiting confirmation on.
            Other option is seding some type of ACK for each message recved which might be worse....
            """
            pass

        else:
            """
            Send log message to broker announcing that the message type is not one we expected.
            """
            pass



    def shutdown(self, sig, frame):
        print "shutting down"
        self.loop.stop()
        self.sub_sock.close()
        self.req_sock.close()
        sys.exit(0)

    def getName(self):
        return self.name

    def getPeers(self):
        return self.peers


    def getRT(self):
        return self.rt




if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--pub-endpoint', dest = 'pub_ep',
                        default = 'tcp://127.0.0.1:23310')
    parser.add_argument('--router-endpoint', dest = 'router_ep',
                        default = 'tcp://127.0.0.1:23311')
    parser.add_argument('--node-name', dest = 'node_name',
                        default = 'test_node')
    parser.add_argument('--spammer', dest ='spammer', action = 'store_true')
    parser.set_defaults(spammer = False)
    parser.add_argument('--peer-names', dest = 'peer_names', default = '')
    args = parser.parse_args()
    args.peer_names = args.peer_names.split(',')

    o = open(args.node_name +".ot", "w")
    e = open(args.node_name +".et", "w")
    sys.stdout = o
    sys.stderr = e
    print "out"
    Node(args.node_name, args.pub_ep, args.router_ep, args.spammer,
         args.peer_names).start()


