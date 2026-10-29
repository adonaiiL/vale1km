#!/usr/bin/env bash
# Vale1Km: instalação via apt com limite de tempo e novas tentativas. Uso: apt_instalar pacote1 pacote2 ...
# (o apt das máquinas do GitHub às vezes trava de vez, e antes isso custava 15 min a 1 h)
apt_instalar() {
  export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
  local opts=(-o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::http::Timeout=20
              -o Acquire::https::Timeout=20 -o Dpkg::Lock::Timeout=120)
  local t
  for t in 1 2 3 4; do
    echo "$(date -u +%T) apt: tentativa $t para: $*"
    if sudo timeout 180 apt-get "${opts[@]}" update -qq > /tmp/apt_update.log 2>&1 \
       && sudo timeout 420 apt-get "${opts[@]}" install -y -qq "$@" > /tmp/apt_install.log 2>&1; then
      echo "$(date -u +%T) apt: ok"
      return 0
    fi
    echo "$(date -u +%T) apt falhou ou travou; final dos logs:"
    tail -4 /tmp/apt_update.log 2>/dev/null || true
    tail -6 /tmp/apt_install.log 2>/dev/null || true
    sudo pkill -f 'apt-get' 2>/dev/null || true
    sudo dpkg --configure -a > /dev/null 2>&1 || true
    sleep 5
  done
  echo "ERRO: não consegui instalar $* com o apt"
  return 1
}
