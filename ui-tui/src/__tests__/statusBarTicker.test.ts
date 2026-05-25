import { describe, expect, it } from 'vitest'

import { memoryProfileLabel, padVerb, skillsLabel, VERB_PAD_LEN } from '../components/appChrome.js'
import { VERBS } from '../content/verbs.js'

describe('FaceTicker verb padding', () => {
  it('pads every verb to the same width', () => {
    for (const verb of VERBS) {
      expect(padVerb(verb)).toHaveLength(VERB_PAD_LEN)
    }
  })

  it('keeps trailing ellipsis attached', () => {
    for (const verb of VERBS) {
      expect(padVerb(verb).startsWith(`${verb}…`)).toBe(true)
    }
  })
})

describe('StatusRule memory/profile/skills labels', () => {
  it('formats memory and user profile usage', () => {
    expect(
      memoryProfileLabel({
        calls: 0,
        input: 0,
        memory_chars: 4350,
        memory_limit: 17600,
        output: 0,
        total: 0,
        user_chars: 2225,
        user_limit: 11000
      })
    ).toBe('MEM 4.4k/17.6k · USR 2.2k/11k')
  })

  it('omits memory/profile label when counts are absent', () => {
    expect(memoryProfileLabel({ calls: 0, input: 0, output: 0, total: 0 })).toBe('')
  })

  it('formats skills count', () => {
    expect(skillsLabel({ calls: 0, input: 0, output: 0, skill_count: 40, total: 0 })).toBe('SKL 40')
  })
})
