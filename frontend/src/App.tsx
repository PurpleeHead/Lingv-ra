import { useEffect, useRef, useState } from 'react'
import { request } from './api'

type Localized = { ru: string; en: string }
type Choice = { id: string; text: Localized }
type Token = { id: string; text: string }
type Exercise = {
  id: string
  type: 'choice' | 'text' | 'word_order'
  instruction: Localized
  prompt: Localized
  choices?: Choice[]
  placeholder?: Localized
  tokens?: Token[]
}
type Hint = { level: number; hint: string }
type Lesson = { id: string; title: Localized; description: Localized; level: string; exercise_count: number; available: boolean; completed?: boolean; is_next?: boolean }
type LessonDetail = { id: string; title: Localized; description: Localized; level: string; vocabulary: { slug: string; word: string; translation: string }[]; exercises: Exercise[] }
type Me = { first_name: string; settings: { ui_language: string; daily_goal: number } }
type Dashboard = { timezone: 'UTC'; date: string; current_streak_days: number; course: null | { id:string; title:Localized; completed_lessons:number; total_lessons:number; progress_percent:number; completed_exercises:number; total_exercises:number; next_lesson:null|{id:string;title:Localized;description:Localized} }; today:{exercise_actions:number;vocabulary_review_actions:number;total_actions:number;goal:number;goal_reached:boolean}; recent_activity:{date:string;exercise_actions:number;vocabulary_review_actions:number;total_actions:number}[]; stats:{exercises_attempted:number;correct_answer_submissions:number;unique_exercises_answered_correctly:number;lessons_completed:number;vocabulary_items_due:number;vocabulary_review_submissions:number;unique_vocabulary_words_learned:number} }
type DueWord = { id: number; word: string; next_review_at: string }
type ReviewResult = { id: number; word: string; translation: string; rating: 'again'|'hard'|'good'|'easy'; successful_reviews: number; failed_reviews: number; consecutive_successes: number; interval_days: number; last_reviewed_at: string; next_review_at: string }
type Copy = { [key: string]: string }

const copy: Record<'ru' | 'en', Copy> = {
  ru: { eyebrow:'ТВОЙ МАЛЕНЬКИЙ ШАГ К СВОБОДНОМУ АНГЛИЙСКОМУ', title:'Английский, который входит в привычку.', subtitle:'Короткие уроки. Практика каждый день. Прогресс без перегруза.', start:'Продолжить обучение', lessons:'Твои уроки', vocab:'Словарь', review:'Повторить слова', due:'к повторению', progress:'Прогресс', daily:'Цель на день', minutes:'минут', loading:'Загружаем уроки…', retry:'Повторить загрузку', reveal:'Показать перевод', again:'Не помню', hard:'С трудом', good:'Помню', easy:'Легко', reviewing:'Сохраняем оценку…', reviewSaved:'Оценка сохранена. Следующий повтор:', reviewNext:'Дальше', reviewDone:'Повторение завершено', reviewEmpty:'Сейчас нет слов для повтора. Новые слова появятся здесь, когда наступит время.', reviewError:'Не удалось загрузить или сохранить повтор. Обнови список и попробуй ещё раз.', reviewProgress:'Слов в этой сессии', back:'Назад к урокам', check:'Проверить ответ', next:'Следующее задание', correct:'Верно! Отличная работа.', wrong:'Пока неверно. Попробуй ещё раз.', api:'Не удалось связаться с API. Убедись, что backend запущен.', local:'Локальный режим разработки', done:'Урок завершён!', completed:'Ты прошёл этот урок. Маленькие шаги складываются в большой результат.', home:'К урокам', word:'Слово', translation:'Перевод', language:'Язык интерфейса', progressCount:'правильных ответов', remove:'Сбросить ответ', hint:'Подсказка', hintLevel:'Уровень', hintError:'Не удалось загрузить подсказку. Попробуй ещё раз.', hintUnavailable:'Для этого задания подсказка пока недоступна.', retryHint:'Повторить запрос' },
  en: { eyebrow:'YOUR SMALL STEP TOWARDS FLUENT ENGLISH', title:'English that becomes a habit.', subtitle:'Short lessons. Daily practice. Progress without overwhelm.', start:'Continue learning', lessons:'Your lessons', vocab:'Vocabulary', review:'Review words', due:'due', progress:'Progress', daily:'Daily goal', minutes:'minutes', loading:'Loading lessons…', retry:'Retry loading', reveal:'Reveal translation', again:'Again', hard:'Hard', good:'Good', easy:'Easy', reviewing:'Saving rating…', reviewSaved:'Rating saved. Next review:', reviewNext:'Continue', reviewDone:'Review complete', reviewEmpty:'No words are due right now. Words will appear here when their review is due.', reviewError:'Could not load or save the review. Refresh the list and try again.', reviewProgress:'Words in this session', back:'Back to lessons', check:'Check answer', next:'Next exercise', correct:'Correct! Great job.', wrong:'Not quite. Try again.', api:'Could not connect to the API. Make sure the backend is running.', local:'Local development mode', done:'Lesson complete!', completed:'You finished this lesson. Small steps add up to big progress.', home:'Back to lessons', word:'Word', translation:'Translation', language:'Interface language', progressCount:'correct answers', remove:'Reset answer', hint:'Hint', hintLevel:'Level', hintError:'Could not load the hint. Try again.', hintUnavailable:'A hint is not available for this exercise yet.', retryHint:'Retry request' },
}

export default function App() {
  const [lang, setLang] = useState<'ru' | 'en'>('ru')
  const [lessons, setLessons] = useState<Lesson[]>([])
  const [me, setMe] = useState<Me | null>(null)
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [goalSaving, setGoalSaving] = useState(false)
  const [active, setActive] = useState<LessonDetail | null>(null)
  const [step, setStep] = useState(0)
  const [answer, setAnswer] = useState<string | string[]>('')
  const [feedback, setFeedback] = useState('')
  const [wasCorrect, setWasCorrect] = useState<boolean | null>(null)
  const [hints, setHints] = useState<Hint[]>([])
  const [hintLoading, setHintLoading] = useState(false)
  const [hintError, setHintError] = useState<'missing' | 'error' | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const submissionLock = useRef(false)
  const hintLock = useRef(false)
  const hintGeneration = useRef(0)
  const hintController = useRef<AbortController | null>(null)
  const [error, setError] = useState('')
  const [vocab, setVocab] = useState<{word:string;translation:string}[]>([])
  const [dueCount, setDueCount] = useState<number | null>(null)
  const [reviewItems, setReviewItems] = useState<DueWord[] | null>(null)
  const [reviewTranslation, setReviewTranslation] = useState('')
  const [reviewResult, setReviewResult] = useState<ReviewResult | null>(null)
  const [reviewTotal, setReviewTotal] = useState(0)
  const [reviewDone, setReviewDone] = useState(0)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [reviewSubmitting, setReviewSubmitting] = useState(false)
  const reviewLock = useRef(false)
  const t = copy[lang]

  useEffect(() => {
    let alive = true
    async function loadDashboard() {
      setLoading(true)
      setError('')
      const userResult = await Promise.allSettled([request<Me>('/api/v1/me')]).then(results => results[0])
      const [lessonResult, dueResult] = await Promise.allSettled([
        request<Lesson[]>('/api/v1/lessons'),
        request<DueWord[]>('/api/v1/review/due'),
      ])
      const dashboardResult = await Promise.allSettled([request<Dashboard>('/api/v1/dashboard')]).then(results => results[0])
      if (!alive) return
      if (lessonResult.status === 'fulfilled') setLessons(lessonResult.value)
      if (userResult.status === 'fulfilled') {
        setMe(userResult.value)
        const language = userResult.value.settings.ui_language
        if (language === 'ru' || language === 'en') setLang(language)
      }
      if (dashboardResult.status === 'fulfilled') setDashboard(dashboardResult.value)
      if (dueResult.status === 'fulfilled') setDueCount(dueResult.value.length)
      if ([lessonResult, userResult, dueResult, dashboardResult].some(result => result.status === 'rejected')) setError(t.api)
      setLoading(false)
    }
    void loadDashboard()
    return () => { alive = false }
  }, [])

  function resetAnswer() {
    hintGeneration.current += 1
    hintController.current?.abort()
    hintController.current = null
    hintLock.current = false
    setHintLoading(false)
    setAnswer('')
    setFeedback('')
    setWasCorrect(null)
    setHints([])
    setHintError(null)
  }

  async function revealHint() {
    if (!active || !exercise || hintLock.current || wasCorrect) return
    const level = hints.length + 1
    if (level > 2) return
    hintLock.current = true
    const generation = hintGeneration.current
    const controller = new AbortController()
    hintController.current = controller
    setHintLoading(true)
    setHintError(null)
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    try {
      const hint = await request<Hint>(`/api/v1/lessons/${active.id}/exercises/${exercise.id}/hints/${level}`, { signal: controller.signal })
      if (generation === hintGeneration.current) setHints(items => [...items, hint])
    } catch (failure) {
      if (generation === hintGeneration.current) {
        setHintError(failure instanceof Error && failure.message.includes('Hint not available') ? 'missing' : 'error')
      }
    }
    finally {
      window.clearTimeout(timeout)
      if (generation === hintGeneration.current) {
        hintController.current = null
        hintLock.current = false
        setHintLoading(false)
      }
    }
  }

  async function openLesson(id: string) {
    setError('')
    resetAnswer()
    try { setActive(await request<LessonDetail>(`/api/v1/lessons/${id}`)); setStep(0) }
    catch { setError(t.api) }
  }

  async function checkAnswer() {
    if (submissionLock.current || !active || !exercise || answer === '' || (Array.isArray(answer) && answer.length === 0)) return
    submissionLock.current = true
    setSubmitting(true)
    setError('')
    try {
      const result = await request<{correct:boolean; explanation:string; lesson_completed:boolean}>(`/api/v1/lessons/${active.id}/answer`, {
        method: 'POST', body: JSON.stringify({ exercise_id: exercise.id, answer }),
      })
      setWasCorrect(result.correct)
      setFeedback(`${result.correct ? t.correct : t.wrong} ${result.explanation}`)
      if (result.lesson_completed) setLessons(items => {
        const updated = items.map(item => item.id === active.id ? { ...item, completed: true } : item)
        const nextId = updated.find(item => !item.completed)?.id
        return updated.map(item => ({ ...item, is_next: item.id === nextId }))
      })
      request<Dashboard>('/api/v1/dashboard').then(setDashboard).catch(() => setError(t.api))
    } catch { setError(t.api) }
    finally { submissionLock.current = false; setSubmitting(false) }
  }

  function next() {
    if (!active) return
    if (step + 1 >= active.exercises.length) { setActive(null); resetAnswer(); return }
    setStep(value => value + 1)
    resetAnswer()
  }

  async function showVocab() {
    setActive(null); setReviewItems(null); setError('')
    try { setVocab(await request<{word:string;translation:string}[]>('/api/v1/vocabulary')) }
    catch { setError(t.api) }
  }

  async function startReview() {
    setActive(null); setVocab([]); setReviewItems([]); setReviewTranslation(''); setReviewResult(null); setError('')
    setReviewLoading(true)
    try {
      const items = await request<DueWord[]>('/api/v1/review/due')
      setReviewItems(items)
      setDueCount(items.length)
      setReviewTotal(items.length)
      setReviewDone(0)
    } catch { setError(t.reviewError); setReviewItems(null) }
    finally { setReviewLoading(false) }
  }

  async function revealTranslation() {
    const item = reviewItems?.[0]
    if (!item || reviewTranslation || reviewLoading) return
    setReviewLoading(true); setError('')
    try {
      const result = await request<{id:number; translation:string}>(`/api/v1/vocabulary/${item.id}/translation`)
      setReviewTranslation(result.translation)
    } catch { setError(t.reviewError) }
    finally { setReviewLoading(false) }
  }

  async function rateWord(rating: ReviewResult['rating']) {
    const item = reviewItems?.[0]
    if (!item || !reviewTranslation || reviewResult || reviewLock.current) return
    reviewLock.current = true; setReviewSubmitting(true); setError('')
    try {
      const result = await request<ReviewResult>(`/api/v1/vocabulary/${item.id}/review`, {
        method: 'POST', body: JSON.stringify({ rating }),
      })
      setReviewResult(result)
      setReviewDone(count => count + 1)
      setDueCount(count => Math.max(0, (count ?? 1) - 1))
      request<Dashboard>('/api/v1/dashboard').then(setDashboard).catch(() => setError(t.api))
    } catch { setError(t.reviewError) }
    finally { reviewLock.current = false; setReviewSubmitting(false) }
  }

  function continueReview() {
    if (!reviewResult) return
    setReviewItems(items => items ? items.slice(1) : null)
    setReviewTranslation(''); setReviewResult(null)
  }

  async function changeLang(next: 'ru' | 'en') {
    setLang(next)
    try { await request('/api/v1/me/settings', { method:'PATCH', body:JSON.stringify({ui_language:next}) }) }
    catch { /* Keep the selected interface language available for this session. */ }
  }

  async function changeGoal(goal: number) {
    if (goalSaving || !me) return
    setGoalSaving(true)
    setError('')
    try {
      const updated = await request<Me['settings']>('/api/v1/me/settings', { method:'PATCH', body:JSON.stringify({daily_goal:goal}) })
      setMe({ ...me, settings: { ...me.settings, daily_goal: updated.daily_goal } })
      setDashboard(await request<Dashboard>('/api/v1/dashboard'))
    } catch { setError(t.api) }
    finally { setGoalSaving(false) }
  }

  const exercise = active?.exercises[step]
  const selectedTokens = Array.isArray(answer) ? answer : []
  const selectedLabel = exercise?.type === 'word_order'
    ? selectedTokens.map(id => exercise.tokens?.find(token => token.id === id)?.text ?? '').join(' ')
    : ''
  const completedLessonCount = lessons.filter(lesson => lesson.completed).length
  const courseProgress = lessons.length ? Math.round(completedLessonCount / lessons.length * 100) : 0

  return <main className="app-shell">
    <header className="topbar"><a className="brand" href="#" onClick={event => { event.preventDefault(); setActive(null) }}><span className="brand-mark">L</span><span>Lingvéra</span></a><div className="top-actions"><span className="streak" aria-label={lang==='ru'?'Текущая серия учебных дней':'Current learning streak'}>✦ <b>{dashboard?.current_streak_days ?? 0}</b> <small>{lang==='ru'?'дней подряд':'day streak'}</small></span><div className="lang-switch"><button className={lang==='ru'?'chosen':''} onClick={()=>changeLang('ru')}>RU</button><button className={lang==='en'?'chosen':''} onClick={()=>changeLang('en')}>EN</button></div></div></header>
    <section className="hero"><div className="hero-copy"><span className="eyebrow"><span className="dot"/> {t.eyebrow}</span><h1>{t.title}</h1><p>{t.subtitle}</p><a className="primary-button" href="#lessons" onClick={event=>{event.preventDefault();document.getElementById('lessons')?.scrollIntoView({behavior:'smooth'})}}>{t.start}<span>↗</span></a><div className="hero-meta"><span>◷ 5–10 {t.minutes}</span><span>✧ A1 beginner</span><span>♡ Learn at your pace</span></div></div><div className="hero-art" aria-hidden="true"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="floating-card card-word"><small>WORD OF THE DAY</small><strong>hello<span>!</span></strong><em> /həˈləʊ/</em><div className="word-translation">привет · greeting</div></div><div className="floating-card card-progress"><div className="progress-ring">✦</div><div><strong>+1</strong><small>new skill</small></div></div><span className="sparkle sparkle-one">✳</span><span className="sparkle sparkle-two">✦</span></div></section>
    {error&&<div className="error-banner" role="alert">{error} <button className="text-button" onClick={()=>window.location.reload()}>{t.retry}</button></div>}
    {reviewItems!==null?<section className="lesson-panel review-panel"><button className="back-button" onClick={()=>setReviewItems(null)}>← {t.back}</button>{reviewLoading&&<p className="muted" role="status">{t.loading}</p>}{error&&<div className="review-error" role="alert">{error}<button className="text-button" onClick={()=>void startReview()}>{t.retry}</button></div>}{!reviewLoading&&reviewItems.length===0&&<div className="review-complete"><span className="review-symbol" aria-hidden="true">✦</span><h2>{t.reviewDone}</h2><p>{reviewTotal===0?t.reviewEmpty:`${reviewDone} / ${reviewTotal} · ${t.reviewDone}`}</p><button className="primary-button" onClick={()=>setReviewItems(null)}>{t.home}</button></div>}{reviewItems[0]&&<><div className="review-session-progress"><span>{t.reviewProgress}: {reviewDone} / {reviewTotal}</span><div className="progress-line" role="progressbar" aria-label={t.reviewProgress} aria-valuemin={0} aria-valuemax={reviewTotal} aria-valuenow={reviewDone}><span style={{width:`${reviewTotal?reviewDone/reviewTotal*100:0}%`}}/></div></div><article className="review-card"><span className="question-kicker">{t.word}</span><h2 lang="en">{reviewItems[0].word}</h2>{reviewTranslation?<div className="review-translation" lang={lang}>{reviewTranslation}</div>:<button className="primary-button reveal-button" disabled={reviewLoading} onClick={()=>void revealTranslation()}>{t.reveal}</button>}{reviewTranslation&&!reviewResult&&<div className="review-ratings" aria-label={lang==='ru'?'Оцените, насколько вы вспомнили слово':'Rate how well you remembered'}>{(['again','hard','good','easy'] as const).map(rating=><button key={rating} className={`rating-button rating-${rating}`} disabled={reviewSubmitting} onClick={()=>void rateWord(rating)}>{reviewSubmitting?t.reviewing:t[rating]}</button>)}</div>}{reviewResult&&<div className="review-feedback" role="status"><p>{t.reviewSaved} {new Date(reviewResult.next_review_at).toLocaleString(lang==='ru'?'ru-RU':'en-US')}</p><p>{t[reviewResult.rating]} · {reviewResult.interval_days===0?'10 min':`${reviewResult.interval_days} ${lang==='ru'?'дн.':'days'}`}</p><button className="primary-button" onClick={continueReview}>{t.reviewNext}<span>→</span></button></div>}</article></>}</section>:active&&exercise?<section className="lesson-panel"><button className="back-button" onClick={()=>{resetAnswer();setActive(null)}}>← {t.back}</button><div className="lesson-heading"><span className="level-pill">{active.level}</span><span className="step-label">{step+1} / {active.exercises.length}</span></div><div className="step-track"><span style={{width:`${((step+1)/active.exercises.length)*100}%`}}/></div><h2>{active.title[lang]}</h2><p className="lesson-description">{active.description[lang]}</p>{active.vocabulary?.length>0&&<div className="lesson-vocabulary" aria-label={lang==='ru'?'Слова урока':'Lesson vocabulary'}>{active.vocabulary.map(item=><span key={item.slug}><strong lang="en">{item.word}</strong><small>{item.translation}</small></span>)}</div>}<div className="question-card"><span className="question-kicker">{exercise.instruction[lang]}</span><h3>{exercise.prompt[lang]}</h3>
      {exercise.type==='choice'&&<div className="answer-options">{exercise.choices?.map(option=><button key={option.id} className={`answer-option ${answer===option.id?'selected':''}`} onClick={()=>{setAnswer(option.id);setFeedback('');setWasCorrect(null)}}><span className="option-radio">{answer===option.id?'✓':''}</span>{option.text[lang]}</button>)}</div>}
      {exercise.type==='text'&&<input className="answer-option" aria-label={exercise.instruction[lang]} value={typeof answer==='string'?answer:''} placeholder={exercise.placeholder?.[lang]} onChange={event=>{setAnswer(event.target.value);setFeedback('');setWasCorrect(null)}} onKeyDown={event=>{if(event.key==='Enter')void checkAnswer()}} />}
      {exercise.type==='word_order'&&<><p className="lesson-description">{selectedLabel || '…'}</p><div className="answer-options">{exercise.tokens?.map(token=><button key={token.id} className={`answer-option ${selectedTokens.includes(token.id)?'selected':''}`} disabled={selectedTokens.includes(token.id)} onClick={()=>{setAnswer([...selectedTokens,token.id]);setFeedback('');setWasCorrect(null)}}><span className="option-radio">{selectedTokens.includes(token.id)?'✓':''}</span>{token.text}</button>)}</div><button className="text-button" onClick={resetAnswer}>{t.remove}</button></>}
      {feedback&&<div className={`feedback ${wasCorrect?'good':'try-again'}`} role="status">{feedback}</div>}
      {!wasCorrect&&<div className="exercise-hints" aria-label={t.hint}>
        {hints.map(item=><p key={item.level} className="exercise-hint" role="status"><strong>{t.hint} {t.hintLevel} {item.level}:</strong> {item.hint}</p>)}
        {hintError&&<p className="hint-error" role="alert">{hintError==='missing'?t.hintUnavailable:t.hintError}</p>}
        {hints.length<2&&<button className="text-button hint-button" type="button" aria-label={`${hintError?t.retryHint:t.hint} ${t.hintLevel} ${hints.length+1}`} disabled={hintLoading||submitting} onClick={()=>void revealHint()}>{hintLoading?t.loading:hintError?t.retryHint:`${t.hint} ${t.hintLevel} ${hints.length+1}`}</button>}
      </div>}
      <div className="question-footer"><span>✦ Learn by doing</span>{wasCorrect?<button className="primary-button" onClick={next}>{step+1===active.exercises.length?t.done:t.next}<span>→</span></button>:<button className="primary-button" disabled={submitting||answer===''||(Array.isArray(answer)&&answer.length===0)} onClick={()=>void checkAnswer()}>{submitting?t.loading:t.check}<span>→</span></button>}</div></div></section>:active&&!exercise?<section className="lesson-panel"><h2>{t.done}</h2><p>{t.completed}</p><button className="primary-button" onClick={()=>setActive(null)}>{t.home}</button></section>:<section id="lessons" className="content-section"><div className="section-heading"><div><span className="eyebrow">YOUR LEARNING PATH</span><h2>{t.lessons}</h2><p>Build confidence one small win at a time.</p></div><div className="section-actions"><button className="text-button" onClick={()=>void startReview()}>{t.review} ({dueCount??'…'} {t.due})</button><button className="text-button" onClick={()=>void showVocab()}>{t.vocab} <span>↗</span></button></div></div>{loading?<p className="muted">{t.loading}</p>:lessons.length===0?<div className="empty-state"><p className="muted">{error?t.api:t.lessons}</p><button className="text-button" onClick={()=>window.location.reload()}>{t.retry}</button></div>:<><div className="course-progress-summary"><div><strong>{completedLessonCount} / {lessons.length}</strong><span>{lang==='ru'?'уроков завершено':'lessons completed'} · {courseProgress}%</span></div><div className="progress-line" role="progressbar" aria-label={lang==='ru'?'Прогресс курса':'Course progress'} aria-valuemin={0} aria-valuemax={100} aria-valuenow={courseProgress}><span style={{width:`${courseProgress}%`}}/></div></div><div className="lesson-grid">{lessons.map((lesson,index)=><article className={`lesson-card ${lesson.is_next?'lesson-card-next':''}`} key={lesson.id}><div className={`lesson-icon icon-${index%3}`}>{['✳','◈','✦'][index%3]}</div><div className="lesson-card-top"><span className="level-pill">{lesson.level}</span><span className="availability-label">{lesson.completed?(lang==='ru'?'Пройдено':'Completed'):(lesson.available?(lang==='ru'?'Доступен':'Available'):(lang==='ru'?'Закрыт':'Locked'))}</span><span className="duration">{lesson.completed?'✓ ':''}◷ 5 min</span></div><h3>{lesson.title[lang]}</h3><p>{lesson.description[lang]}</p>{lesson.is_next&&<span className="next-lesson-label">{lang==='ru'?'Следующий урок':'Next lesson'}</span>}<div className="card-bottom"><span>{lesson.exercise_count} {lang==='ru'?'упражнений':'quick exercises'}</span><button aria-label={`${lang==='ru'?'Открыть':'Open'} ${lesson.title[lang]}`} onClick={()=>void openLesson(lesson.id)}>→</button></div></article>)}</div></>}{vocab.length>0&&<div className="vocab-panel"><h3>{t.vocab}</h3><div className="vocab-list">{vocab.map(item=><div className="vocab-row" key={item.word}><strong>{item.word}</strong><span>{item.translation}</span></div>)}</div></div>}<div className="bottom-grid"><article className="daily-card daily-dashboard"><div className="daily-icon" aria-hidden="true">◷</div><div className="daily-content"><span className="eyebrow">{lang==='ru'?'ТВОЙ РИТМ':'YOUR ROUTINE'}</span><h3>{t.daily}</h3><p>{lang==='ru'?'Цель считается по правильным ответам и сохранённым повторам — не по времени в приложении.':'Goal counts correct answers and saved reviews, not time in the app.'}</p><div className="goal-presets" aria-label={lang==='ru'?'Цель учебных действий':'Daily learning action goal'}>{[5,10,15].map(goal=><button key={goal} type="button" disabled={goalSaving} aria-pressed={(dashboard?.today.goal??me?.settings.daily_goal)===goal} className={(dashboard?.today.goal??me?.settings.daily_goal)===goal?'selected':''} onClick={()=>void changeGoal(goal)}>{goal}</button>)}</div></div><div className="daily-number">{dashboard?.today.total_actions??0}<small> / {dashboard?.today.goal??me?.settings.daily_goal??10} {lang==='ru'?'действий':'actions'}</small></div></article><article className="progress-card"><div className="progress-title"><span className="eyebrow">{lang==='ru'?'АНАЛИТИКА':'LEARNING STATS'}</span><span className="progress-badge">{dashboard?.current_streak_days??0} {lang==='ru'?'дн. серия':'day streak'}</span></div><h3>{t.progress}</h3><p>{dashboard?.course?.completed_lessons??0} / {dashboard?.course?.total_lessons??0} {lang==='ru'?'уроков ·':'lessons ·'} {dashboard?.course?.progress_percent??0}%</p><div className="progress-line" role="progressbar" aria-label={lang==='ru'?'Прогресс курса':'Course progress'} aria-valuemin={0} aria-valuemax={100} aria-valuenow={dashboard?.course?.progress_percent??0}><span style={{width:`${dashboard?.course?.progress_percent??0}%`}}/></div><small className="muted">{lang==='ru'?'Попытки':'Attempts'}: {dashboard?.stats.exercises_attempted??0} · {lang==='ru'?'верные ответы':'correct submissions'}: {dashboard?.stats.correct_answer_submissions??0} · {lang==='ru'?'уникальные слова':'unique words'}: {dashboard?.stats.unique_vocabulary_words_learned??0} · {lang==='ru'?'повторы':'reviews'}: {dashboard?.stats.vocabulary_review_submissions??0}</small><div className="dashboard-links"><button className="text-button" onClick={()=>void startReview()}>{lang==='ru'?'К повторению':'Due for review'}: {dashboard?.stats.vocabulary_items_due??dueCount??0}</button>{dashboard?.course?.next_lesson&&<button className="text-button" onClick={()=>void openLesson(dashboard.course!.next_lesson!.id)}>{lang==='ru'?'Продолжить':'Continue'}: {dashboard.course.next_lesson.title[lang]}</button>}</div></article></div><div className="weekly-activity"><strong>{lang==='ru'?'Учебные действия за 7 дней (UTC)':'Learning actions, last 7 UTC days'}</strong><div className="activity-bars">{(dashboard?.recent_activity??[]).map(day=><div className="activity-day" key={day.date} title={`${day.date}: ${day.total_actions}`}><span className="activity-bar" style={{height:`${Math.max(4,Math.min(100,day.total_actions*12))}%`}}/><small>{new Date(`${day.date}T12:00:00Z`).toLocaleDateString(lang==='ru'?'ru-RU':'en-US',{weekday:'short'})}</small><b>{day.total_actions}</b></div>)}</div></div></section>}
    <footer><a className="brand footer-brand" href="#"><span className="brand-mark">L</span><span>Lingvéra</span></a><span>Made for curious minds, one word at a time.</span><span className="footer-status"><i/> {t.local}</span></footer>
  </main>
}
