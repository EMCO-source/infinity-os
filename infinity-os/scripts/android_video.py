"""Bounded owner-only H.264 remux stream. No recorded files."""
import subprocess,time,select,os

def stream(handler,android):
    capture=subprocess.Popen([android.adb,'-s',android.serial,'exec-out','screenrecord','--output-format=h264','--bit-rate','1500000','--time-limit','180','-'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    mux=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-fflags','+genpts','-probesize','32','-analyzeduration','0','-use_wallclock_as_timestamps','1','-f','h264','-i','pipe:0','-an','-c:v','copy','-movflags','frag_keyframe+empty_moov+default_base_moof','-frag_duration','100000','-flush_packets','1','-f','mp4','pipe:1'],stdin=capture.stdout,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    capture.stdout.close()
    try:
        handler.send_response(200);handler.send_header('Content-Type','video/mp4');handler.send_header('Cache-Control','no-store');handler.send_header('X-Content-Type-Options','nosniff');handler.end_headers();handler.close_connection=True
        end=time.monotonic()+185
        while time.monotonic()<end:
            if not handler.authenticated():break
            ready,_,_=select.select([mux.stdout],[],[],2)
            if not ready:
                if mux.poll() is not None:break
                continue
            data=os.read(mux.stdout.fileno(),65536)
            if not data:break
            handler.wfile.write(data);handler.wfile.flush()
    except (BrokenPipeError,ConnectionResetError):pass
    finally:
        for p in [mux,capture]:
            if p.poll() is None:p.terminate()
        for p in [mux,capture]:
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait()
