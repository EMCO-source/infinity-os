"""Bounded timestamp-preserving scrcpy transport. Owner-only route supplies auth/lock.
No audio, recording, account access, public listener or persistent adb forward.
"""
import socket,struct,subprocess,time,secrets

MAX_PACKET=4*1024*1024
CONFIG=1<<62
KEY=1<<61
PTS_MASK=(1<<61)-1

def read_exact(sock,size):
    data=bytearray()
    while len(data)<size:
        part=sock.recv(size-len(data))
        if not part:raise EOFError('Android video ended')
        data.extend(part)
    return bytes(data)

def read_packet(sock):
    header=read_exact(sock,12)
    flags,size=struct.unpack('>QI',header)
    if not 0<size<=MAX_PACKET:raise ValueError('Invalid video packet size')
    return header+read_exact(sock,size)

def stream(handler,android):
    scid=secrets.randbelow(0x7fffffff)
    command=[android.adb,'-s',android.serial]
    result=subprocess.run(command+['forward','tcp:0','localabstract:scrcpy_%08x'%scid],capture_output=True,text=True,check=True)
    port=int(result.stdout.strip())
    capture=None;sock=None
    try:
        capture=subprocess.Popen(command+['shell','CLASSPATH=/data/local/tmp/scrcpy-server-v5.0.1.jar','app_process','/','com.genymobile.scrcpy.Server','5.0.1',f'scid={scid:08x}','tunnel_forward=true','audio=false','control=false','cleanup=false','send_device_meta=false','send_dummy_byte=false','send_stream_meta=false','max_size=1040','max_fps=60','video_bit_rate=1500000'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+8
        first=None
        while time.monotonic()<deadline:
            try:
                sock=socket.create_connection(('127.0.0.1',port),timeout=1);sock.settimeout(2)
                first=read_packet(sock);break
            except (OSError,EOFError):
                if sock:sock.close();sock=None
                time.sleep(.15)
        if first is None:raise ValueError('Timestamped encoder did not start')
        handler.send_response(200)
        handler.send_header('Content-Type','application/octet-stream')
        handler.send_header('Cache-Control','no-store, no-transform')
        handler.send_header('X-Content-Type-Options','nosniff')
        handler.send_header('X-Accel-Buffering','no')
        handler.end_headers();handler.close_connection=True
        handler.wfile.write(first);handler.wfile.flush()
        end=time.monotonic()+180
        while time.monotonic()<end:
            if not handler.authenticated() or handler.principal['role'] not in ('owner','visitor'):break
            try:packet=read_packet(sock)
            except socket.timeout:continue
            handler.wfile.write(packet);handler.wfile.flush()
    except (BrokenPipeError,ConnectionResetError,EOFError):pass
    finally:
        if sock:sock.close()
        if capture and capture.poll() is None:
            capture.terminate()
            try:capture.wait(timeout=3)
            except subprocess.TimeoutExpired:capture.kill();capture.wait()
        subprocess.run(command+['forward','--remove',f'tcp:{port}'],capture_output=True)
