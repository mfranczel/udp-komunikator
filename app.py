from PyInquirer import prompt       # !! needs to be installed with pip !!
import socket
import queue
import math
import os
import libscrc._crc16               # !! needs to be installed with pip !!
import threading

# turns on alteration of fragments, so that they are handled as corrupted on receiving end
ALTERED = True
# doesn't send some of the fragments, so that they are handled as missing on receiving end
MISSING = False

# initial fragment is of type 1, has 0 bytes stored in data, has 0 index and total
initial_fragment = (1).to_bytes(1, "big") + (0).to_bytes(2, "big") + (0).to_bytes(2, "big") + (0).to_bytes(2,"big")

default_client_menu = [
        {
            'type': 'input',
            'message': 'Enter valid ip of receiver:',
            'name': 'ip',
            'validate': lambda val: check_ip(val) or "Please, enter valid address."
        },
        {
            'type': 'input',
            'message': 'Enter port of receiver (1-65535):',
            'name': 'port',
            'validate': lambda val: (check_if_integer(val) and 1 <= int(val) <= 65535) or "Please, enter number in range 1-65535"
        },
        {
            'type': 'input',
            'message': 'Enter maximum fragment size (1-1463, 0 for auto):',
            'name': 'fragment_size',
            'validate': lambda val: (check_if_integer(val) and 0 <= int(val) <= 1463) or "Please, enter number in range 1-1463"
        },
        {
            'type': 'list',
            'message': 'Do you want to send file or message?',
            'name': 'fm',
            'choices': ['File', 'Message']
        },
        {
            'type': 'input',
            'message': 'Enter file path:',
            'when': lambda answers: answers['fm'] == 'File',
            'name': 'file_path',
            'validate': lambda val: os.path.isfile(val) or "File you've entered does not exist"
        },
        {
            'type': 'input',
            'message': 'Enter message:',
            'when': lambda answers: answers['fm'] == 'Message',
            'name': 'message',
        },
        {
            'type': 'list',
            'message': 'Do you want some fragments to be corrupted?',
            'name': 'corr',
            'choices': ['Yes', 'No']
        },

]

default_server_menu = {
        'type': 'input',
        'message': 'Enter port of reciever (1-65535):',
        'name': 'port',
        'validate': lambda val: (check_if_integer(val) and 1 <= int(val) <= 65535) or "Please, enter number in range 1-65535"
}

same_server_menu = [
        {
            'type': 'input',
            'message': 'Enter maximum fragment size (1-1463, 0 for auto):',
            'name': 'fragment_size',
            'validate': lambda val: (check_if_integer(val) and 0 <= int(val) <= 1463) or "Please, enter number in range 1-1463"
        },
        {
            'type': 'list',
            'message': 'Do you want to send file or message?',
            'name': 'fm',
            'choices': ['File', 'Message']
        },
        {
            'type': 'input',
            'message': 'Enter file path:',
            'when': lambda answers: answers['fm'] == 'File',
            'name': 'file_path',
            'validate': lambda val: os.path.isfile(val) or "File you've entered does not exist"
        },
        {
            'type': 'input',
            'message': 'Enter message:',
            'when': lambda answers: answers['fm'] == 'Message',
            'name': 'message',
        }
]

end_menu = {
        'type': 'list',
        'message': 'Select how you wish to continue: ',
        'name': 'selection',
        'choices': ['Send data to the same server', 'Send data to different server', 'Change to server', 'Quit']
}

server_end_menu = {
        'type': 'list',
        'message': 'Select how you wish to continue: ',
        'name': 'selection',
        'choices': ['Receive more data', 'Change to client', 'Quit']
}

def check_if_integer(val):
    """
    Checks whether value is convertible to integer

    :param val: valuethat needs to be checked
    :return: boolean
    """
    try:
        int(val)
    except:
        return False
    return True

def parser(data):
    """
    Parses data fragment into dictionary
    :param data: data to be parsed
    :return: dictionary of information from data
    """
    fragment = {'type': int.from_bytes(data[0:1], "big"), 'data_length': int.from_bytes(data[1:3], "big"),
                'total_n': int.from_bytes(data[3:5], "big"), 'order': int.from_bytes(data[5:7], "big"),
                'data': data[7:]}
    return fragment

def make_fragments(message, fragment_size):
    """
    Makes fragments from byte message of certain size

    :param message: message represented as bytearray
    :param fragment_size: size of fragments to be made
    :return: queue of created fragments
    """
    fragment_queue = queue.Queue()
    start = 0
    index = 0

    # if maximum fragment size is not set, set maximum possible fragment size
    if fragment_size == 0:
        if len(message) >= 1463:
            fragment_size = 1463
        else:
            fragment_size = len(message)

    n_of_fragments = int(math.ceil(float(len(message)) / float(fragment_size)))

    # if fragment size is larger than actual size of fragment, change it to size of fragment
    if fragment_size > len(message):
        fragment_size = len(message)

    end = fragment_size

    print(f"Fragments of maximum size of {fragment_size} are going to be sent.")
    # slices message from start til end
    while True:

        if start + fragment_size >= len(message):
            end = len(message)
            fragment = message[start:end]
            # fragment is created with 2 as a type, set fragment size, number of fragments, index, data and generated crc
            fragment = (2).to_bytes(1, "big") + (fragment_size).to_bytes(2, "big") + (n_of_fragments).to_bytes(2,
                                                                                                                     "big") + (
                           index).to_bytes(2, "big") + fragment
            fragment += libscrc.ibm(fragment[7:]).to_bytes(2, "big")
            fragment_queue.put(fragment)
            break
        else:
            fragment = message[start:end]
            # fragment is created with 2 as a type, set fragment size, number of fragments, index, data and generated crc
            fragment = (2).to_bytes(1, "big") + (fragment_size).to_bytes(2, "big") + (n_of_fragments).to_bytes(2,
                                                                                                                     "big") + (
                           index).to_bytes(2, "big") + fragment
            fragment += libscrc.ibm(fragment[7:]).to_bytes(2, "big")
            index += 1
            start += fragment_size
            end += fragment_size
            fragment_queue.put(fragment)

    return fragment_queue


def keep_alive(e, sock, ip, port):
    """
    Sends keep alive messages til it's stopped
    :param e: Event that is set when keep_alive needs to stop
    :param sock: socket for sending keep alive messages
    :param ip: ip address of receiver
    :param port: port of receiver
    """
    while not e.isSet():
        is_set = e.wait(25)
        if not is_set:
            keep_alive_fragment = (4).to_bytes(1, "big") + (0).to_bytes(2, "big") + (0).to_bytes(2, "big") + (0).to_bytes(2,"big")
            sock.sendto(keep_alive_fragment, (ip, port))


def display_end_menu(ip, port, sock):
    """
    Displays end menu after all fragments have been sent
    :param ip: IP of former receiver
    :param port: PORT of former receiver
    :param sock: socket to be recycled if user continues to send data
    """
    e = threading.Event()
    thread = threading.Thread(target=keep_alive, daemon=True, args=(e, sock, ip, port))
    thread.start()

    answer = prompt(end_menu)['selection']

    if answer == 'Send data to different server':
        e.set()
        start_client()
    elif answer == 'Send data to the same server':
        answers = prompt(same_server_menu)
        message = open(answers['file_path'], "rb").read() if answers['fm'] == 'File' else bytearray(
            answers['message'], "ascii")
        message_type = 1 if answers['fm'] == 'Message' else 2
        if message_type == 1:
            file_path = 0
        else:
            file_path = answers['file_path']
        e.set()
        send(ip, int(answers['fragment_size']), port, message, file_path, sock)
    elif answer == 'Change to server':
        e.set()
        start_server()

def send(ip, fragment_size, port, message, path, sock_et=0):
    """
    Sends message to chosen receiver

    :param ip: IP address of receiver
    :param fragment_size: maximum size of fragments to be sent
    :param port: port of receiver
    :param message: message to be sent (either file or text message, both being bytearrays)
    :param path: path to file to be sent, it's 0 if message is just text message
    :param sock_et: socket that is passed on if it was already created (in last iteration)
    """
    # create socket if it wasn't already created (e.g. in last iteration)
    if sock_et == 0:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # send fragment for initialization and wait for response for max. two seconds
        sock.settimeout(2)
        sock.sendto(initial_fragment, (ip, port))
        try:
            data, address = sock.recvfrom(2048)
            if (int.from_bytes(data[0:1], "big") == 1):
                print("Connection was initialized successfully.")
        except:
            # if connection was unsuccessful, start again
            print("Error occurred while connecting to the server. Please try again.")
            start_client()
            return
    else:
        sock = sock_et

    fragments_queue = make_fragments(message, fragment_size)

    if path != 0:
        print(f"File {os.path.abspath(path)} is going to be transfered.")

    print(f"{fragments_queue.qsize()} fragments are going to be sent.")

    # filename fragment, if only a simple text message is being sent, it creates just header without data
    if path == 0:
        # data fragment with empty data is created - that means a message is being sent
        fragment = (2).to_bytes(1, "big") + (0).to_bytes(2, "big") + (fragments_queue.qsize()).to_bytes(2, "big") + (0).to_bytes(2,
                                                                                                                    "big")
    else:
        filename = os.path.basename(path)
        # data fragment with filename in data is created
        fragment = (2).to_bytes(1, "big") + (len(filename)).to_bytes(2, "big") + (fragments_queue.qsize()).to_bytes(2, "big") + (
            0).to_bytes(2, "big") + bytes(filename, "ascii")

    sock.sendto(fragment, (ip, port))

    # copies all fragments in case of unsuccessful delivery
    all_fragments = list(fragments_queue.queue)

    global ALTERED
    global MISSING
    failed_count = 0
    batch_count = 0
    # sends data fragments while queue is not empty
    while not fragments_queue.empty():
        count = 0
        while count != 10 and not fragments_queue.empty():
            fragment = fragments_queue.get()
            # if some fragments need to be altered in case of testing of error detection
            if ALTERED and count%2 == 0 :
                fragment = bytearray(fragment)
                failed_count += 1
                try:
                    fragment[7] = fragment[7]+1
                except ValueError:
                    fragment[7] = fragment[7]-1
                fragment = bytes(fragment)
                if failed_count > 10:
                    ALTERED = False
            # if MISSING is true, first fragment is not sent for error detection
            if not MISSING:
                sock.sendto(fragment, (ip, port))
            else:
                MISSING = False
            count += 1
        while True:
            # waits for confirmation message - if all fragments arrived as they should, nothing much happens
            # otherwise fragments that arrived corrupted are put into queue again
            data, address = sock.recvfrom(1024)
            if int.from_bytes(data[0:1], "big") == 5:
                print(f"Batch {batch_count} delivered successfully.")
                batch_count += 1
                break
            elif int.from_bytes(data[0:1], "big") == 3:
                n_of_failed = int(int.from_bytes(data[3:5], "big"))
                for i in range(n_of_failed):
                    fragments_queue.put(all_fragments[int.from_bytes(data[7+i*2:7+i*2+2], "big")])
                print(f"Batch {batch_count} delivered unsuccessfully.")
                failed = ""
                for i in range(n_of_failed):
                    failed += str(int.from_bytes(data[7+i*2:7+i*2+2], "big")) + " "
                print(f"Fragments [ {failed}] were unsuccessful in their delivery.")
                batch_count += 1
                break

    display_end_menu(ip, port, sock)


def check_ip(IP):
    """
    Checks if IP is valid or not
    :param IP: IP to be checked
    :return: Boolean
    """
    try:
        socket.inet_aton(IP)
    except:
        return False
    return True


def start_client():
    """
    Starts client, opens menu and calls send function with arguments entered by user in menu
    """

    answers = prompt(default_client_menu)
    message = open(answers['file_path'], "rb").read() if answers['fm'] == 'File' else bytearray(answers['message'], "ascii")

    message_type = 1 if answers['fm'] == 'Message' else 2
    if message_type == 1:
        file_path = 0
    else:
        file_path = answers['file_path']

    global ALTERED

    if answers['corr'] == 'Yes':
        ALTERED = True
    else:
        ALTERED = False

    send(answers['ip'], int(answers['fragment_size']), int(answers['port']), message, file_path)


def start_server():
    """
    Starts server, listens until connection is initialised and file or message is received
    """
    ip_addr = "0.0.0.0"

    answers = prompt(default_server_menu)
    port = int(answers['port'])

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((ip_addr, port))

    # listens until connection is initialised by client
    print(f"Listening on port {port}")
    while True:
        sock.settimeout(None)
        while True:
            # checks whether it is first iteration or not. If it is, it waits for initialisation
            # otherwise it skips that part
            try:
                data
            except:
                data, address = sock.recvfrom(2048)
                parsed_data = parser(data)
                if parsed_data['type'] == 1:
                    print("Connection initialized by client")
                    sock.sendto(data, address)
                data, address = sock.recvfrom(2048)

            parsed_data = parser(data)
            total_fragments = parsed_data['total_n']
            print(f"{total_fragments} fragments are going to be received.")

            # when data length of first fragment is 0, no filename was sent. That means that message is incoming.
            if parsed_data['data_length'] == 0:
                print("Message is to be received.")
                typ = 1
                break
            else:
                print("File is to be received")
                typ = 2
                filename = data[7:].decode("ascii")
                break

        # Starts to receive fragments until all are not received
        counter = total_counter = 0
        to_be_reviewed = []
        reviewed = {}
        failed = []
        end_data = bytearray()
        sock.settimeout(1)

        while total_counter != total_fragments:
            # when no fragment is received when it should, it sends info. to client about missing fragment/s
            try:
                data, address = sock.recvfrom(2048)
            except:
                print(f"Batch no. {int(total_counter / 2)} was corrupted.")

                if total_counter - counter + 10 > total_fragments:
                    for i in range(total_fragments-total_counter+counter):
                        failed.append(total_counter-counter+i)
                else:
                    for i in range(10):
                        failed.append(total_counter-counter+i)

                ack = (3).to_bytes(1, "big") + (len(failed) * 2).to_bytes(2, "big") + (len(failed)).to_bytes(2,
                                                                                                             "big") + (
                          0).to_bytes(2, "big")

                for i in failed:
                    ack += i.to_bytes(2, "big")
                sock.sendto(ack, address)
                failed = []
                to_be_reviewed = []
                total_counter -= counter
                counter = 0
                continue

            counter += 1
            total_counter += 1
            fragment = data[:]
            to_be_reviewed.append(fragment)

            if total_counter == 1:
                print(f"Maximum fragment size was set to {int.from_bytes(fragment[1:3], 'big')} by client.")

            # when full batch or last batch is received, it is checked
            if counter % 10 == 0 or total_counter == total_fragments:

                for i in to_be_reviewed:
                    if int.from_bytes(i[len(i) - 2:], "big") == libscrc.ibm(i[7:len(i) - 2]):
                        reviewed[int.from_bytes(i[5:7], "big")] = i[7:len(i) - 2]
                    else:
                        total_counter -= 1
                        failed.append(int.from_bytes(i[5:7], "big"))

                if len(failed) == 0:
                    print(f"Received batch no.{int(total_counter / 10)} without any error [fragments {total_counter - counter}-{total_counter}]")
                    # positive ack fragment is created (type 5, size, index and total set to 0)
                    ack = (5).to_bytes(1, "big") + (0).to_bytes(2, "big") + (0).to_bytes(2, "big") + (
                        0).to_bytes(2, "big")
                    sock.sendto(ack, address)
                else:
                    # when there are corrupted fragments, send their ids to client so they are sent again
                    print(f"Batch no. {int(total_counter/10)} was corrupted.")
                    # negative ack is created (type 3, size that includes indexes stored in data...)
                    ack = (3).to_bytes(1, "big") + (len(failed) * 2).to_bytes(2, "big") + (len(failed)).to_bytes(2, "big") + (0).to_bytes(2,"big")
                    corrupted = ""
                    for i in failed:
                        ack += i.to_bytes(2, "big")
                        corrupted += str(i) + " "
                    print(f"Fragments [ {corrupted}] where corrupted or missing.")
                    sock.sendto(ack, address)
                failed = []
                to_be_reviewed = []
                counter = 0

        for i in range(len(reviewed)):
            try:
                end_data += reviewed[i]
            except:
                pass

        # print out message if it was a message, otherwise save file and print path
        if typ == 1:
            message = end_data.decode("ascii")
            print(f"Message: {message}")
        else:
            file = open(filename, "wb")
            file.write(end_data)
            print(f"File path to the file: {os.path.dirname(os.path.realpath(__file__))}/{filename}")
            file.close()

        # wait for keep alive messages or for new incoming file for up to 30 seconds
        sock.settimeout(30)
        try:
            while True:
                data, address = sock.recvfrom(1024)
                if int.from_bytes(data[:1], 'little') == 4:
                    print("Connection is kept alive by client.")
                    sock.settimeout(30)
                elif int.from_bytes(data[:1], 'little') == 2:
                    break

        except:
            # when 30 seconds pass without any message show menu
            print("Time has elapsed. Client has been disconnected.")
            answer = prompt(server_end_menu)['selection']
            if answer == 'Change to client':
                start_client()
                sock.close()
                break
            elif answer == 'Quit':
                break
            elif answer == 'Receive more data':
                del data
                continue


def main():
    """
    Starts the whole application, let's user choose between client and server.
    """
    client_or_server = {
        'type': 'list',
        'message': 'Select if you want to act as client or server',
        'name': 'cs',
        'choices': ['Client', 'Server']
    }

    answer = prompt(client_or_server)['cs']
    if answer == 'Client':
        start_client()
    else:
        start_server()


if __name__ == "__main__":
    main()
