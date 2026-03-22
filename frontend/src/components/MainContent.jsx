import { useNavigate } from 'react-router-dom'

export default function MainContent({
  searchQuery,
  onSearchChange,
  onGoHome,
  children,
}) {
  const navigate = useNavigate()

  return (
    <main className="main-content main-content--home">
      <div className="home-main-header home-main-header--ruled">
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
          className="header-try-cta"
          onClick={() => navigate('/chat')}
          aria-label="Try Lex (opens chat)"
        >
          <span className="header-try-cta__label">Try Lex</span>
        </button>
      </div>

      {children}
    </main>
  )
}
