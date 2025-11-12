# Frontend Dashboard TODO

## Goal
Create a simple, interactive React dashboard for end-users to run QA automation tests. Focus on core functionality: query input, test execution, and results display.

## Initial Setup
We will use `npx create-react-app` to initialize the React project, then proceed with building the components.
- Run `npx create-react-app frontend --template typescript` to create the initial project structure
- After initial setup, we will start building the dashboard components

## Core Features (MVP)

### 1. Layout Structure
- **Header**: Logo, user info, navigation
- **Left Sidebar**: Navigation menu (Dashboard, Test History)
- **Main Dashboard**: Query input form and test execution area
- **Footer**: Copyright, links

### 2. Query Input & Test Execution
- Text input field for user query/task
- Optional start URL input
- "Run Test" button
- Loading state during execution
- Real-time step counter display

### 3. Test Results Display
- Show test status (running, completed, error)
- Display step-by-step progress
- Show final report when completed
- Display errors if any

### 4. API Integration
- Connect to `/api/v1/workflow/run` endpoint
- Handle request/response properly
- Error handling for API failures

## Technology Stack
- **React** (with TypeScript recommended)
- **Axios/Fetch** for API calls
- **CSS/Tailwind** for styling (modern, clean design)
- **React Router** (optional, for navigation)

## File Structure
```
frontend/
├── src/
│   ├── components/
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   ├── Footer.tsx
│   │   ├── QueryForm.tsx
│   │   ├── TestResults.tsx
│   │   └── Dashboard.tsx
│   ├── services/
│   │   └── api.ts
│   ├── App.tsx
│   └── index.tsx
├── package.json
└── README.md
```

## API Endpoints Used
- `POST /api/v1/workflow/run`
  - Request: `{ task: string, start_url?: string, max_steps?: number }`
  - Response: `{ task, completed, step_count, verification_status, report, error }`

## Production Enhancements (Future)

### Phase 1: Enhanced UX
- [ ] Test history persistence (localStorage or backend)
- [ ] Test result export (JSON/PDF)
- [ ] Copy/share test results
- [ ] Dark mode toggle

### Phase 2: Real-time Updates
- [ ] WebSocket/SSE for live step updates
- [ ] Progress bar with percentage
- [ ] Live browser screenshot display (if available)
- [ ] Step-by-step action visualization

### Phase 3: Advanced Features
- [ ] Test scheduling
- [ ] Test templates/presets
- [ ] Multiple test runs comparison
- [ ] Performance metrics visualization

### Phase 4: Enterprise Features
- [ ] User authentication
- [ ] Team collaboration
- [ ] Test suites management
- [ ] API rate limiting handling
- [ ] Usage analytics dashboard

## Design Principles
1. **Simplicity**: Focus on core functionality, avoid feature bloat
2. **User-Friendly**: Clear, intuitive interface for non-technical users
3. **Responsive**: Works on desktop and tablet
4. **Fast**: Quick load times, efficient API calls
5. **Clean**: Modern, professional SaaS design

## Implementation Notes
- Use environment variables for API base URL
- Handle loading states gracefully
- Show helpful error messages
- Implement proper TypeScript types for API responses
- Use React hooks for state management
- Consider using React Query/SWR for API state management
