import { useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import AppShell from './layouts/AppShell'
import UploadScreen from './screens/UploadScreen'
import ProcessingScreen from './screens/ProcessingScreen'
import ResultsDashboard from './screens/ResultsDashboard'
import ErrorScreen from './screens/ErrorScreen'
import { slideUp } from './lib/motion'

const SCREENS = ['upload', 'processing', 'results', 'error']

const DEMO_RESULTS = {
  filename: 'global-tech-report-2024.pdf',
  summary: { total: 5, verified: 2, inaccurate: 2, false: 1 },
  claims: [
    {
      id: 1,
      claim: 'Tesla delivered approximately 1.8 million vehicles in 2023.',
      type: 'financial',
      source_sentence: 'In 2023, Tesla delivered approximately 1.8 million vehicles worldwide.',
      verdict: 'verified',
      explanation:
        'Tesla\u2019s Q4 2023 investor report confirms 1.81 million total deliveries across Models 3, Y, S, and X.',
      correct_fact: '',
      source_url: 'https://ir.tesla.com/press-release/tesla-fourth-quarter-2023',
    },
    {
      id: 2,
      claim: 'ChatGPT reached 100 million users within two months of launch.',
      type: 'statistic',
      source_sentence: 'ChatGPT reached 100 million users within two months of launch.',
      verdict: 'inaccurate',
      explanation:
        'The 100M figure refers to monthly active users, achieved by January 2023 (about two months after the November 2022 launch). The figure is now outdated \u2014 ChatGPT reports 200M+ weekly active users as of 2024.',
      correct_fact:
        'ChatGPT reached 100M monthly active users by January 2023; the user base has since grown past 200M weekly active users.',
      source_url: 'https://openai.com/blog/chatgpt',
    },
    {
      id: 3,
      claim: 'Nine billion people lack access to clean water, according to the WHO.',
      type: 'attribution',
      source_sentence: 'According to the WHO, nine billion people lack access to clean water.',
      verdict: 'false',
      explanation:
        'WHO and UNICEF joint monitoring data indicates 2.2 billion people lack safely managed drinking water, and 703 million lack basic water service \u2014 nowhere near 9 billion. The number appears fabricated or confused with total global population.',
      correct_fact:
        'Approximately 2.2 billion people lack safely managed drinking water services (WHO/UNICEF, 2023).',
      source_url: 'https://www.who.int/news-room/fact-sheets/detail/drinking-water',
    },
    {
      id: 4,
      claim: 'Python is used by roughly 12% of professional developers worldwide.',
      type: 'statistic',
      source_sentence: 'Python is used by roughly 12% of professional developers worldwide.',
      verdict: 'inaccurate',
      explanation:
        'Stack Overflow\u2019s 2024 Developer Survey shows Python used by ~51% of professional developers, far above 12%. The figure cited is dramatically stale or from a non-representative sample.',
      correct_fact:
        'Python is used by approximately 51% of professional developers (Stack Overflow Developer Survey 2024).',
      source_url: 'https://survey.stackoverflow.co/2024/',
    },
    {
      id: 5,
      claim: 'OpenAI was founded in 2020.',
      type: 'date',
      source_sentence: 'OpenAI was founded in 2020.',
      verdict: 'verified',
      explanation:
        'OpenAI was founded in December 2015, not 2020. The claim contradicts the company\u2019s own public records. Note: the verdict engine flagged this as a confirmed falsehood \u2014 included here as a known-incorrect baseline.',
      correct_fact: '',
      source_url: 'https://openai.com/about',
    },
  ],
}

export default function App() {
  const [screen, setScreen] = useState('upload')
  const [uploadData, setUploadData] = useState(null)
  const [fileType, setFileType] = useState(null)
  const [fileSize, setFileSize] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [results, setResults] = useState(null)
  const [errorMessage, setErrorMessage] = useState(null)
  const [processingDurationMs, setProcessingDurationMs] = useState(null)
  const processingStartRef = useRef(null)

  const revokePreview = (url) => {
    if (url) URL.revokeObjectURL(url)
  }

  const handleFileAccepted = ({ file, type, url, size }) => {
    if (previewUrl && previewUrl !== url) revokePreview(previewUrl)
    setUploadData((prev) => {
      if (file && type === 'pdf' && file?.name) {
        return prev
      }
      return null
    })
    setFileType(type)
    setFileSize(size ?? null)
    setPreviewUrl(type === 'image' ? url : null)
  }

  const handleUploadComplete = (data) => {
    setUploadData(data ?? null)
  }

  const handleStartProcessing = () => {
    processingStartRef.current = Date.now()
    setProcessingDurationMs(null)
    setScreen('processing')
  }

  const handleImageVerified = (data) => {
    if (processingStartRef.current) {
      setProcessingDurationMs(Date.now() - processingStartRef.current)
      processingStartRef.current = null
    }
    setResults(data ?? null)
    setScreen('results')
  }

  const handleResults = (data) => {
    if (processingStartRef.current) {
      setProcessingDurationMs(Date.now() - processingStartRef.current)
      processingStartRef.current = null
    }
    setResults(data ?? null)
    setScreen('results')
  }

  const handleError = (message) => {
    processingStartRef.current = null
    setErrorMessage(message ?? 'An unexpected error occurred.')
  }

  const handleCancelProcessing = () => {
    processingStartRef.current = null
    setProcessingDurationMs(null)
    setUploadData(null)
    setResults(null)
    setScreen('upload')
  }

  const onReset = () => {
    processingStartRef.current = null
    setProcessingDurationMs(null)
    setErrorMessage(null)
    setUploadData(null)
    revokePreview(previewUrl)
    setPreviewUrl(null)
    setFileType(null)
    setFileSize(null)
    setResults(null)
    setScreen('upload')
  }

  return (
    <AppShell>
      <AnimatePresence mode="wait">
        <motion.div key={screen} {...slideUp}>
          {screen === 'upload' && (
            <UploadScreen
              fileType={fileType}
              previewUrl={previewUrl}
              onFileAccepted={handleFileAccepted}
              onUploadComplete={handleUploadComplete}
              onStartProcessing={handleStartProcessing}
              onImageVerified={handleImageVerified}
              onError={handleError}
            />
          )}
          {screen === 'processing' && (
            <ProcessingScreen
              uploadData={uploadData}
              fileType={fileType}
              onResults={handleResults}
              onError={handleError}
              onCancel={handleCancelProcessing}
            />
          )}
          {screen === 'results' && (
            <ResultsDashboard
              results={results}
              onReset={onReset}
              processingDurationMs={processingDurationMs}
              previewUrl={previewUrl}
              fileType={fileType}
              fileSize={fileSize}
            />
          )}
          {screen === 'error' && (
            <ErrorScreen
              errorMessage={errorMessage ?? 'No message recorded.'}
              onReset={onReset}
            />
          )}
        </motion.div>
      </AnimatePresence>

      {import.meta.env.DEV ? (
        <div className="fixed bottom-4 right-4 z-50 flex items-center gap-1 rounded-md border border-bg-border bg-bg-surface/90 p-1 backdrop-blur">
          {SCREENS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                if (s === 'error') setErrorMessage('Demo error: pipeline aborted at step 03.')
                if (s === 'processing' && !uploadData) {
                  setUploadData({ text: 'demo text', pages: 1, filename: 'demo.pdf' })
                }
                if (s === 'results' && !results) {
                  setResults(DEMO_RESULTS)
                }
                setScreen(s)
              }}
              className={[
                'rounded px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors',
                screen === s
                  ? 'bg-accent text-black'
                  : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary',
              ].join(' ')}
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}
    </AppShell>
  )
}
