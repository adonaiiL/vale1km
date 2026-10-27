#!/usr/bin/env bash
# Vale1Km: instalação via apt com limite de tempo e novas tentativas. Uso: apt_instalar pacote1 pacote2 ...
# (o apt das máquinas do GitHub às vezes trava de vez, e antes isso custava 15 min a 1 h)
apt_instalar() {
  # sudo zera o ambiente: DEBIAN_FRONTEND tem de ir na linha do sudo, senão o debconf espera até o timeout
  local sudoenv=(DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a)
  local opts=(-o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::http::Timeout=30
              -o Acquire::https::Timeout=30 -o Dpkg::Lock::Timeout=120)
  local t rc
  for t in 1 2 3 4; do
    echo "$(date -u +%T) apt: tentativa $t para: $*"
    rc=0
    sudo "${sudoenv[@]}" timeout 180 apt-get "${opts[@]}" update -qq > /tmp/apt_update.log 2>&1 \
      && sudo "${sudoenv[@]}" timeout 600 apt-get "${opts[@]}" install -y "$@" > /tmp/apt_install.log 2>&1 \
      || rc=$?
    if [ "$rc" -eq 0 ]; then
      echo "$(date -u +%T) apt: ok"
      return 0
    fi
    echo "$(date -u +%T) apt falhou ou travou (código $rc); final dos logs:"
    tail -8 /tmp/apt_update.log 2>/dev/null || true
    tail -20 /tmp/apt_install.log 2>/dev/null || true
    sudo pkill -f 'apt-get' 2>/dev/null || true
    sudo "${sudoenv[@]}" dpkg --configure -a > /dev/null 2>&1 || true
    sleep 5
  done
  echo "ERRO: não consegui instalar $* com o apt"
  return 1
}
