-- 팀 상세 타임라인: {{team_key}}의 모든 신호, 최신순. program_label은 선정 프로그램의 한국어 이름(없으면 코드 그대로).
SELECT s.signal_date, s.branch, s.source, s.program,
       COALESCE(pr.label, NULLIF(s.program, ''))  AS program_label,
       NULLIF(s.venue, '')                        AS venue,
       s.signal_date > CURRENT_DATE               AS is_upcoming     -- 예정 공연·기간 끝 날짜로 저장된 선정
FROM signals s
LEFT JOIN programs pr ON pr.program = s.program
WHERE s.team_key = {{team_key}}
ORDER BY s.signal_date DESC, s.branch;
