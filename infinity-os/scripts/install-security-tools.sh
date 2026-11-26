#!/usr/bin/env bash
# INFINITY OS - security training toolset installer (Debian 12 guest)
# Installs a comprehensive pentest/cybersecurity toolchain.
# Resumable-ish: apt phases are idempotent; failures are logged, not fatal.
export DEBIAN_FRONTEND=noninteractive
export HOME=/root
export PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin:/root/.local/bin

freemb() { df --output=avail -m / | tail -1 | tr -d ' '; }
guard() {
  f=$(freemb)
  echo "[guard] free=${f}MB after: $1"
  if [ "$f" -lt 400 ]; then echo "[guard] LOW SPACE - stopping further installs"; exit 42; fi
}

A="apt-get install -y --no-install-recommends"

echo "=== phase 0: base ==="
apt-get update -qq
$A git curl wget ca-certificates unzip p7zip-full python3-pip python3-venv pipx vim tmux htop jq tree screen rsync sqlite3 build-essential ruby-full ruby-dev libcurl4-openssl-dev libimage-exiftool-perl || echo "FAILED phase0"
apt-get clean; guard base

echo "=== phase 1: metasploit (Rapid7 omnibus) ==="
if ! command -v msfconsole >/dev/null; then
  curl -fsSL https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb -o /tmp/msfinstall && chmod 755 /tmp/msfinstall && /tmp/msfinstall || echo "FAILED metasploit"
fi
apt-get clean; guard metasploit

echo "=== phase 2: network recon + sniffing ==="
$A nmap masscan arp-scan netdiscover fping hping3 dnsutils whois traceroute mtr-tiny tcpdump tshark dsniff ettercap-text-only mitmproxy socat netcat-openbsd telnet ftp snmp onesixtyone smbclient samba-common-bin nfs-common ike-scan sipvicious || echo "FAILED phase2"
apt-get clean; guard recon

echo "=== phase 3: web + password attacks ==="
$A nikto sqlmap dirb gobuster wfuzz wapiti whatweb hydra medusa ncrack john hashcat cewl crunch sslscan testssl.sh || echo "FAILED phase3"
apt-get clean; guard web

echo "=== phase 4: wireless + forensics + RE + privacy ==="
$A aircrack-ng reaver bully wifite hcxtools hcxdumptool binwalk foremost scalpel steghide stegsnow testdisk dcfldd dc3dd hashdeep sleuthkit gdb ltrace strace checksec elfutils lynis python3-impacket python3-scapy python3-pwntools tor torsocks proxychains4 openvpn wireguard-tools || echo "FAILED phase4"
apt-get clean; guard forensics

echo "=== phase 5: wordlists ==="
mkdir -p "/usr/share/wordlists/seclists/Discovery/Web-Content" "/usr/share/wordlists/seclists/Discovery/DNS" /usr/share/wordlists/seclists/Usernames /usr/share/wordlists/seclists/Passwords
[ -s /usr/share/wordlists/rockyou.txt ] || curl -fsSL https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt -o /usr/share/wordlists/rockyou.txt || echo "FAILED rockyou"
base=https://raw.githubusercontent.com/danielmiessler/SecLists/master
for f in "Discovery/Web-Content/common.txt" "Discovery/Web-Content/directory-list-2.3-medium.txt" "Discovery/Web-Content/raft-small-words.txt" "Discovery/Web-Content/big.txt" "Discovery/DNS/subdomains-top1million-5000.txt" "Usernames/top-usernames-shortlist.txt" "Usernames/cirt-default-usernames.txt" "Passwords/Common-Credentials/10k-most-common.txt" "Passwords/darkweb2017-top10000.txt" "Passwords/xato-net-10-million-passwords-10000.txt"; do
  [ -s "/usr/share/wordlists/seclists/$f" ] || curl -fsSL "$base/$f" -o "/usr/share/wordlists/seclists/$f" || echo "FAILED $f"
done
guard wordlists

echo "=== phase 6: exploitdb + git tools ==="
[ -d /opt/exploitdb ] || git clone --depth 1 https://gitlab.com/exploit-database/exploitdb.git /opt/exploitdb || echo "FAILED exploitdb"
if [ -f /opt/exploitdb/searchsploit ]; then
  ln -sf /opt/exploitdb/searchsploit /usr/local/bin/searchsploit
  sed -i 's|/opt/exploit-database/exploitdb|/opt/exploitdb|g' /opt/exploitdb/.searchsploit_rc 2>/dev/null
  cp /opt/exploitdb/.searchsploit_rc /root/.searchsploit_rc 2>/dev/null
fi
[ -d /opt/responder ] || git clone --depth 1 https://github.com/lgandx/Responder /opt/responder
chmod +x /opt/responder/Responder.py 2>/dev/null; ln -sf /opt/responder/Responder.py /usr/local/bin/responder
[ -d /opt/commix ] || git clone --depth 1 https://github.com/commixproject/commix /opt/commix
ln -sf /opt/commix/commix.py /usr/local/bin/commix
[ -d /opt/enum4linux-ng ] || git clone --depth 1 https://github.com/cddmp/enum4linux-ng /opt/enum4linux-ng
ln -sf /opt/enum4linux-ng/enum4linux-ng.py /usr/local/bin/enum4linux-ng
mkdir -p /opt/privesc
[ -d /opt/privesc/PEASS-ng ] || git clone --depth 1 https://github.com/carlospolop/PEASS-ng /opt/privesc/PEASS-ng
[ -d /opt/privesc/linux-exploit-suggester ] || git clone --depth 1 https://github.com/The-Z-Labs/linux-exploit-suggester /opt/privesc/linux-exploit-suggester
ln -sf /opt/privesc/linux-exploit-suggester/linux-exploit-suggester.sh /usr/local/bin/linux-exploit-suggester
ln -sf /opt/privesc/PEASS-ng/linPEAS/linpeas.sh /usr/local/bin/linpeas
[ -d /opt/gef ] || git clone --depth 1 https://github.com/hugsy/gef /opt/gef
echo 'source /opt/gef/gef.py' > /root/.gdbinit
guard gittools

echo "=== phase 7: go binaries (nuclei, subfinder, httpx, ffuf) ==="
mkdir -p /opt/gobins
tmpd=$(mktemp -d)
dl() {
  url=$(curl -fsSL "https://api.github.com/repos/$1/releases/latest" | jq -r ".assets[] | select(.name | test(\"$2\")) | .browser_download_url" | head -1)
  if [ -n "$url" ]; then
    curl -fsSL "$url" -o "$tmpd/pkg" && (cd "$tmpd" && (unzip -o -q pkg -d "$3" 2>/dev/null || tar xzf pkg -C "$3" 2>/dev/null)) || echo "FAILED fetch $1"
  else echo "FAILED url $1"; fi
  rm -f "$tmpd/pkg"
}
dl projectdiscovery/nuclei 'nuclei_.*linux_amd64.zip' /opt/gobins
dl projectdiscovery/subfinder 'subfinder_.*linux_amd64.zip' /opt/gobins
dl projectdiscovery/httpx 'httpx_.*linux_amd64.zip' /opt/gobins
dl ffuf/ffuf 'ffuf_.*linux_amd64.tar.gz' /opt/gobins
for b in nuclei subfinder httpx ffuf; do [ -f /opt/gobins/$b ] && chmod +x /opt/gobins/$b && ln -sf /opt/gobins/$b /usr/local/bin/$b; done
rm -rf "$tmpd"
guard gobins

echo "=== phase 8: pip tools ==="
pip3 install --break-system-packages --quiet volatility3 sslyze shodan name-that-hash hashid sublist3r dirsearch spiderfoot || echo "FAILED some pip tools"
pipx install netexec || echo "FAILED netexec"
pipx install crackmapexec || echo "FAILED crackmapexec"
for b in /root/.local/bin/*; do [ -f "$b" ] && ln -sf "$b" /usr/local/bin/; done
guard pip

echo "=== phase 9: gems (wpscan, zsteg) ==="
gem install --no-document wpscan zsteg || echo "FAILED gems"
guard gems

echo "=== phase 10: OpenCL runtime for hashcat (CPU) ==="
if [ "$(freemb)" -gt 700 ]; then
  $A pocl-opencl-icd || echo "FAILED pocl"
  apt-get clean
else
  echo "skip pocl (space)"
fi
guard pocl

echo "=== phase 11: nuclei templates ==="
if command -v nuclei >/dev/null; then nuclei -update-templates 2>&1 | tail -2 || true; fi

echo "=== phase 12: OSINT ==="
for p in theharvester recon-ng metagoofil; do
  if apt-cache policy $p 2>/dev/null | grep -q 'Candidate: (none)'; then echo "skip $p (not in Debian)"; else $A $p || echo "FAILED $p"; fi
done
apt-get clean
pip3 install --break-system-packages --quiet sherlock-project maigret holehe h8mail censys ghunt socialscan || echo "FAILED some osint pip tools"
tmpd=$(mktemp -d)
url=$(curl -fsSL "https://api.github.com/repos/sundowndev/phoneinfoga/releases/latest" | jq -r '.assets[] | select(.name | test("linux_amd64.tar.gz")) | .browser_download_url' | head -1)
if [ -n "$url" ]; then curl -fsSL "$url" -o "$tmpd/pi.tar.gz" && tar xzf "$tmpd/pi.tar.gz" -C /opt/gobins 2>/dev/null && chmod +x /opt/gobins/phoneinfoga 2>/dev/null && ln -sf /opt/gobins/phoneinfoga /usr/local/bin/phoneinfoga || echo "FAILED phoneinfoga fetch"; fi
rm -rf "$tmpd"
guard osint

echo "=== cleanup ==="
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/msfinstall /root/.cache/pip
df -h /
echo "=== INSTALL DONE ==="
