import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Limit, Snapshot } from '../types'

const snap = atom({ plugin: 'usage-band', key: 'snap' } as const, null)

const LABEL: Record<string, string> = { five_hour: '5시간', seven_day: '주간', spend_limit: '지출 한도' }

async function refresh($: EngineInterface) {
  const u = await $.session.usage()
  const next: Snapshot = {
    ctxPercent: u.context.percent,
    ctxTokens: u.context.tokens,
    window: u.context.window,
    limits: u.rateLimits.map(r => ({ kind: r.kind, percentUsed: r.percentUsed, resetsAt: r.resetsAt })),
    usd: u.cost?.usd,
    at: await $.clock.now(),
  }
  await update($, snap, () => next)
}

const k = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : `${Math.round(n / 1000)}k`)

function bar(pct: number) {
  const filled = Math.max(0, Math.min(8, Math.round(pct / 12.5)))
  return '▰'.repeat(filled) + '▱'.repeat(8 - filled)
}

function tone(pct: number) {
  return pct >= 90 ? 'error' : pct >= 70 ? 'warning' : 'success'
}

function untilReset(resetsAt: string | undefined, now: number) {
  if (!resetsAt) return ''
  const ms = Date.parse(resetsAt) - now
  if (!Number.isFinite(ms) || ms <= 0) return ''
  const min = Math.round(ms / 60000)
  if (min < 60) return `${min}분 후 초기화`
  const h = Math.floor(min / 60)
  if (h < 48) return `${h}시간 ${min % 60}분 후 초기화`
  return `${Math.floor(h / 24)}일 ${h % 24}시간 후 초기화`
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const r = await next(e)
    await refresh($).catch(() => undefined)
    return r
  })

  // 도구 호출 결과는 그대로 돌려주고, 사용량 갱신은 옆에서 따로 (실패해도 도구 호출에 영향 없음)
  on('tool.call', ($, e, next) => {
    const result = next(e)
    result.then(() => refresh($)).catch(() => undefined)
    return result
  })

  on('turn.complete', async ($, e, next) => {
    const r = await next(e)
    await refresh($).catch(() => undefined)
    return r
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) {
      return next(e)
    }
    const s = await read($, snap)
    if (s === null) {
      return next(e)
    }
    const { Box, Text } = $.ui.resolve(e)
    const now = await $.clock.now()
    const ctx = s.ctxPercent ?? 0

    const limitCell = (l: Limit) => {
      const reset = untilReset(l.resetsAt, now)
      return (
        <Box key={l.kind}>
          <Text dimColor>{LABEL[l.kind] ?? l.kind} </Text>
          <Text color={tone(l.percentUsed)}>{bar(l.percentUsed)} </Text>
          <Text bold>{`${l.percentUsed}%`}</Text>
          <Text dimColor>{reset ? ` (${reset})   ` : '   '}</Text>
        </Box>
      )
    }

    return (
      <Box flexWrap="wrap">
        <Box key="ctx">
          <Text dimColor>컨텍스트 </Text>
          <Text color={tone(ctx)}>{bar(ctx)} </Text>
          <Text bold>{`${ctx}%`}</Text>
          <Text dimColor>{s.ctxTokens != null ? ` (${k(s.ctxTokens)}/${k(s.window)})   ` : '   '}</Text>
        </Box>
        {s.limits.length ? (
          s.limits.map(limitCell)
        ) : (
          <Box key="nolimit">
            <Text dimColor>사용 한도 정보 없음   </Text>
          </Box>
        )}
        {s.usd != null ? (
          <Box key="cost">
            <Text dimColor>비용 </Text>
            <Text bold>{`$${s.usd.toFixed(2)}`}</Text>
          </Box>
        ) : null}
      </Box>
    )
  })
}
