export default function MainContent({
  currentView,
  searchQuery,
  onSearchChange,
  onGoHome,
  onShowChat,
  children,
}) {
  return (
    <main className="main-content main-content--home">
      <div className="home-main-header">
        <button type="button" className="home-header-button" onClick={onGoHome}>
          <h1 className="home-main-title">ParaDocs</h1>
        </button>
        <div className="header-search-wrap">
          <label htmlFor="header-search" className="visually-hidden">
            Search
          </label>
          <input
            id="header-search"
            type="search"
            className="header-search"
            placeholder="Filter by case title"
            autoComplete="off"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-controls="cases-grid"
          />
        </div>
        <button
          type="button"
          className={`header-chat-button${currentView === 'chat' ? ' header-chat-button--active' : ''}`}
          onClick={onShowChat}
        >
          Chat with AI
        </button>
      </div>

      {currentView === 'chat' ? (
        <section className="chat-placeholder" aria-live="polite">
          <h2>AI Chat</h2>
          <p>Chat workspace coming soon.</p>
        </section>
      ) : (
        children
      )}
    </main>
  )
}