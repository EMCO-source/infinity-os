/* Timestamped Annex-B H.264 decoder. No recordings or external assets. */
window.InfinityTimestampVideo=class {
 constructor(canvas,status){this.canvas=canvas;this.status=status;this.abort=new AbortController();this.decoder=null;this.stats={received:0,presented:0,skipped:0,started:performance.now(),firstPTS:null,lastPTS:null};}
 stop(){this.abort.abort();if(this.decoder&&this.decoder.state!=='closed')this.decoder.close();}
 async start(){
  if(!window.VideoDecoder||!window.EncodedVideoChunk)throw Error('Timestamped video is unavailable in this browser');
  let config=null,needKey=true,failure=null;
  this.decoder=new VideoDecoder({output:frame=>{try{this.canvas.width=frame.displayWidth;this.canvas.height=frame.displayHeight;this.canvas.getContext('2d',{alpha:false}).drawImage(frame,0,0);this.stats.presented++;this.stats.lastPTS=frame.timestamp;if(this.stats.firstPTS===null)this.stats.firstPTS=frame.timestamp;const elapsed=(performance.now()-this.stats.started)/1000;this.status.textContent='Timestamped beta · '+(this.stats.presented/elapsed).toFixed(1)+' presented fps · no audio';}finally{frame.close();}},error:e=>{failure=e;this.abort.abort();}});
  const response=await fetch('/api/android/timestamp',{signal:this.abort.signal});
  if(!response.ok)throw Error('Timestamped stream unavailable');
  const reader=response.body.getReader();let pending=new Uint8Array(0);
  while(true){
   const {value,done}=await reader.read();if(done)break;
   const merged=new Uint8Array(pending.length+value.length);merged.set(pending);merged.set(value,pending.length);pending=merged;
   let offset=0;
   while(pending.length-offset>=12){
    const view=new DataView(pending.buffer,pending.byteOffset+offset,12),hi=view.getUint32(0),lo=view.getUint32(4),size=view.getUint32(8);
    if(hi&0x80000000)throw Error('Unexpected video session packet');
    if(!size||size>4194304)throw Error('Invalid video packet');
    if(pending.length-offset<12+size)break;
    const data=pending.slice(offset+12,offset+12+size);offset+=12+size;
    if(hi&0x40000000){
     config=data;let sps=-1;
     for(let i=0;i<data.length-7;i++)if(data[i]===0&&data[i+1]===0&&((data[i+2]===1&&(data[i+3]&31)===7)||(data[i+2]===0&&data[i+3]===1&&(data[i+4]&31)===7))){sps=i+(data[i+2]===1?3:4);break;}
     if(sps<0)throw Error('Encoder configuration missing');
     const codec='avc1.'+Array.from(data.slice(sps+1,sps+4),v=>v.toString(16).padStart(2,'0')).join('');
     const options={codec,optimizeForLatency:true,hardwareAcceleration:'prefer-software'};
     if(!(await VideoDecoder.isConfigSupported(options)).supported)throw Error('This browser cannot decode '+codec);
     this.decoder.configure(options);needKey=true;continue;
    }
    const key=!!(hi&0x20000000),timestamp=(hi&0x1fffffff)*4294967296+lo;this.stats.received++;
    if(failure)throw failure;
    if(this.decoder.decodeQueueSize>4){this.stats.skipped++;needKey=true;continue;}
    if(needKey&&!key){this.stats.skipped++;continue;}
    if(!config)continue;
    let packet=data;
    if(key){packet=new Uint8Array(config.length+data.length);packet.set(config);packet.set(data,config.length);needKey=false;}
    this.decoder.decode(new EncodedVideoChunk({type:key?'key':'delta',timestamp,data:packet}));
   }
   pending=pending.slice(offset);
  }
  if(failure)throw failure;
  throw Error('Timestamped session ended');
 }
};
