from pathlib import Path
import xml.etree.ElementTree as ET
p=Path('/root/.config/openbox/rc.xml')
ns='http://openbox.org/3.4/rc'; ET.register_namespace('',ns)
root=ET.parse('/etc/xdg/openbox/rc.xml');keys=root.getroot().find('{'+ns+'}keyboard')
for key,cmd in [('C-A-b','firefox-esr --no-remote about:blank'),('C-A-f','pcmanfm /root'),('C-A-n','mousepad /root/Notes.txt')]:
 k=ET.SubElement(keys,'{'+ns+'}keybind',{'key':key});act=ET.SubElement(k,'{'+ns+'}action',{'name':'Execute'});ET.SubElement(act,'{'+ns+'}command').text=cmd
apps=root.getroot().find('{'+ns+'}applications')
for klass in ['Pcmanfm','Mousepad','Firefox-esr','XTerm']:
 app=ET.SubElement(apps,'{'+ns+'}application',{'class':klass})
 ET.SubElement(app,'{'+ns+'}maximized').text='yes'
root.write(p,encoding='unicode')
