#!/usr/bin/env bash
# Vale1Km: publica o andamento da rodada no corpo de um release do GitHub (lido pela página do site).
# Uso: progresso.sh PCT "mensagem" [rodando|concluido|erro]
# Sem GH_TOKEN ou sem o gh, não faz nada (rodando localmente, por exemplo).
[ -n "${GH_TOKEN:-}" ] && command -v gh > /dev/null || exit 0
pct="${1:-0}"
msg=$(printf '%s' "${2:-}" | tr -d '"\\\n' | cut -c1-120)
status="${3:-rodando}"
tag="vale1km"
corpo=$(printf '{"pct":%s,"msg":"%s","status":"%s","run":"%s","init":"%s","atualizado":"%s"}' \
  "$pct" "$msg" "$status" "${GITHUB_RUN_ID:-}" "${VALE1KM_INIT:-}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)")
if ! gh release view "$tag" > /dev/null 2>&1; then
  gh release create "$tag" --title "Vale1Km (status e sondagens)" --notes "$corpo" > /dev/null 2>&1 || true
fi
gh release edit "$tag" --notes "$corpo" > /dev/null 2>&1 || true
exit 0
