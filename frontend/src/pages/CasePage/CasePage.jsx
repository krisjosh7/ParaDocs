import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { CircularProgressbarWithChildren, buildStyles } from 'react-circular-progressbar'
import 'react-circular-progressbar/dist/styles.css'
import { VerticalTimeline, VerticalTimelineElement } from 'react-vertical-timeline-component'
import 'react-vertical-timeline-component/style.min.css'
import './CasePage.css'
import ContextUploadPage from '../ContextUploadPage/ContextUploadPage.jsx'
import LiveSession from '../LiveSessionPage/LiveSession.jsx'

const STATUS_ORDER = ['done', 'in_progress', 'upcoming']
const STATUS_LABELS = { done: 'Done', in_progress: 'In Progress', upcoming: 'Upcoming' }

function TaskIcon({ status }) {
  if (status === 'done') {
    return (
      <svg className="task-icon task-icon--done" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="10" cy="10" r="9" stroke="currentColor" strokeWidth="2" />
        <path d="M6 10.5l2.5 2.5 5.5-5.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  if (status === 'in_progress') {
    return <span className="task-icon task-icon--in-progress" aria-hidden="true" />
  }
  return (
    <svg className="task-icon task-icon--upcoming" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="9" stroke="currentColor" strokeWidth="2" />
    </svg>
  )
}

function TimelineDot() {
  return (
    <svg viewBox="0 0 20 20" fill="none" style={{ width: 20, height: 20 }}>
      <circle cx="10" cy="10" r="8" fill="#37456d" stroke="rgba(232, 238, 252, 0.35)" strokeWidth="2" />
      <circle cx="10" cy="10" r="4" fill="#e8eefc" />
    </svg>
  )
}

const timelineContentStyle = {
  background: 'rgba(232, 238, 252, 0.07)',
  color: '#e8eefc',
  border: '1px solid rgba(232, 238, 252, 0.14)',
  borderRadius: '14px',
  boxShadow: '0 4px 16px rgba(5, 10, 24, 0.3)',
  padding: '20px 24px',
}

const timelineArrowStyle = {
  borderRight: '7px solid rgba(232, 238, 252, 0.07)',
}

const timelineIconStyle = {
  background: '#37456d',
  border: '2px solid rgba(232, 238, 252, 0.3)',
  boxShadow: '0 2px 8px rgba(5, 10, 24, 0.25)',
}

const TABS = ['Case Dashboard', 'Discovery', 'Live Session']

export default function CasePage({ cases }) {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [activeTab, setActiveTab] = useState(TABS[0])
  const navRef = useRef(null)
  const tabRefs = useRef({})
  const [bubble, setBubble] = useState({ left: 0, width: 0, ready: false })

  const measureBubble = useCallback(() => {
    const nav = navRef.current
    const btn = tabRefs.current[activeTab]
    if (!nav || !btn) return
    const navRect = nav.getBoundingClientRect()
    const btnRect = btn.getBoundingClientRect()
    setBubble({
      left: btnRect.left - navRect.left,
      width: btnRect.width,
      ready: true,
    })
  }, [activeTab])

  useLayoutEffect(() => {
    measureBubble()
  }, [measureBubble])

  useEffect(() => {
    window.addEventListener('resize', measureBubble)
    return () => window.removeEventListener('resize', measureBubble)
  }, [measureBubble])

  const caseData = useMemo(() => cases.find((c) => c.id === caseId), [cases, caseId])

  const doneCount = useMemo(
    () => (caseData ? caseData.tasks.filter((t) => t.status === 'done').length : 0),
    [caseData],
  )
  const totalCount = caseData ? caseData.tasks.length : 0
  const percentage = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0

  const groupedTasks = useMemo(() => {
    if (!caseData) return {}
    const groups = {}
    for (const s of STATUS_ORDER) {
      const items = caseData.tasks.filter((t) => t.status === s)
      if (items.length > 0) groups[s] = items
    }
    return groups
  }, [caseData])

  const sortedEvents = useMemo(
    () => (caseData ? [...caseData.events].reverse() : []),
    [caseData],
  )
  const isDiscoveryRoute = location.pathname.endsWith('/context-upload')

  useEffect(() => {
    if (isDiscoveryRoute) {
      setActiveTab('Discovery')
    } else if (location.state?.tab) {
      setActiveTab(location.state.tab)
    } else if (activeTab === 'Discovery') {
      setActiveTab('Case Dashboard')
    }
  }, [isDiscoveryRoute])

  function handleTabClick(tab) {
    if (tab === 'Discovery') {
      navigate('/case/' + caseId + '/context-upload')
      return
    }
    if (isDiscoveryRoute) {
      navigate('/case/' + caseId, { state: { tab } })
      return
    }
    setActiveTab(tab)
  }

  if (!caseData) {
    return (
      <div className="app-shell">
        <header className="top-header">
          <button type="button" className="home-header-button" onClick={() => navigate('/')}>
            <h1>ParaDocs</h1>
          </button>
        </header>
        <div className="layout-body">
          <main className="main-content">
            <p className="cases-empty">Case not found.</p>
          </main>
        </div>
      </div>
    )
  }

  return (
    <>
      <header className="top-header">
        <button type="button" className="back-button" aria-label="Back to cases" onClick={() => navigate('/')}>
          <svg viewBox="0 0 24 24" fill="none" width="22" height="22" aria-hidden="true">
            <path d="M15 18l-6-6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <div className="case-header-title">
          <h1>{caseData.title}</h1>
          <p>{caseData.summary}</p>
        </div>
        <nav className="case-nav" ref={navRef}>
          <span
            className="case-nav-bubble"
            style={{
              transform: `translateX(${bubble.left}px)`,
              width: bubble.width,
              opacity: bubble.ready ? 1 : 0,
            }}
          />
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              ref={(el) => { tabRefs.current[tab] = el }}
              className={`case-nav-btn${activeTab === tab ? ' case-nav-btn--active' : ''}`}
              onClick={() => handleTabClick(tab)}
            >
              {tab}
            </button>
          ))}
        </nav>
      </header>

      <div className="layout-body">
        {activeTab === 'Live Session' ? (
          <LiveSession caseId={caseId} />
        ) : isDiscoveryRoute ? (
          <ContextUploadPage caseId={caseId} />
        ) : (
          <main className="main-content case-page-content">
            <div className="case-page-top">
              <section className="task-checklist">
                <h2 className="checklist-heading">Tasks</h2>
                <div className="checklist-scroll">
                  {STATUS_ORDER.map((status) => {
                    const items = groupedTasks[status]
                    if (!items) return null
                    return (
                      <div key={status} className="checklist-group">
                        <h3 className="checklist-group-label">{STATUS_LABELS[status]}</h3>
                        <ul className="checklist-list">
                          {items.map((task) => (
                            <li key={task.id} className={`checklist-item checklist-item--${task.status}`}>
                              <TaskIcon status={task.status} />
                              <span className="checklist-item-label">{task.label}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )
                  })}
                </div>
              </section>

              <div className="case-page-sidebar">
                <div className="stat-card">
                  <h2 className="stat-card-heading">Research Phase</h2>
                  <div className="stat-card-body">
                    <strong className="stat-big-number">10</strong>
                    <span className="stat-description">sources found by agent</span>
                  </div>
                </div>

                <div className="stat-card">
                  <h2 className="stat-card-heading">Progress</h2>
                  <div className="progress-ring-wrap">
                    <CircularProgressbarWithChildren
                      value={percentage}
                      styles={buildStyles({
                        pathColor: '#4a9e6f',
                        trailColor: '#e6dcc4',
                        strokeLinecap: 'round',
                        pathTransitionDuration: 0.5,
                      })}
                      strokeWidth={10}
                    >
                      <strong className="progress-ring-count">{doneCount} of {totalCount}</strong>
                      <span className="progress-ring-label">tasks done</span>
                    </CircularProgressbarWithChildren>
                  </div>
                </div>
              </div>
            </div>

            <section className="case-timeline-section">
              <h2 className="timeline-heading">Timeline</h2>
              <VerticalTimeline layout="2-columns" lineColor="rgba(232, 238, 252, 0.18)" animate={true}>
                {sortedEvents.map((event) => (
                  <VerticalTimelineElement
                    key={event.id}
                    date={event.date}
                    contentStyle={timelineContentStyle}
                    contentArrowStyle={timelineArrowStyle}
                    iconStyle={timelineIconStyle}
                    icon={<TimelineDot />}
                  >
                    <h3 className="timeline-event-title">{event.title}</h3>
                    <p className="timeline-event-desc">{event.description}</p>
                  </VerticalTimelineElement>
                ))}
              </VerticalTimeline>
            </section>
          </main>
        )}
      </div>
    </>
  )
}
