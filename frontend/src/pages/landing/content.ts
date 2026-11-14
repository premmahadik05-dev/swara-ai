import type { IconName } from '../../components/Icons'

/** Everything the landing page says, in one place. Every sentence here describes something the software does today, or says
 *  plainly that it does not. No customer counts, quotes, partner logos, revenue or speed figures: there are none to report. */

export const NAV = [
  { href: '#product', label: 'Product' },
  { href: '#how-it-works', label: 'How it works' },
  { href: '#languages', label: 'Languages' },
  { href: '#technology', label: 'Technology' },
  { href: '#security', label: 'Security' },
  { href: '#contact', label: 'Contact' },
] as const

export const EXAMPLES: { label: string; text: string }[] = [
  { label: 'Hinglish', text: 'Bhai mujhe 2 kilo chawal aur 1 litre doodh chahiye' },
  { label: 'ગુજરાતી', text: 'મને બે કિલો ખાંડ અને એક લિટર દૂધ જોઈએ છે' },
  { label: 'हिन्दी', text: 'भैया ढाई किलो चीनी और आधा किलो चायपत्ती दे दो' },
  { label: 'English', text: 'one and a half kilo onion and a dozen eggs please' },
  { label: 'Gujarati + English', text: 'મને 2 kg sugar અને 1 litre milk જોઈએ' },
]

/** Screenshots of the running app. `scripts/take_screenshots.py --landing` makes them; they show generated demo data. */
export const SHOTS = {
  dashboard: { src: '/shots/dashboard.webp', w: 1440, h: 900, alt: 'The SWARA AI dashboard: seven-day sales, orders, average order value and a restock list, with a sales trend chart.' },
  'order-desk': { src: '/shots/order-desk.webp', w: 1440, h: 900, alt: 'The Order desk: a customer message on the left and the bill being built on the right, with each item priced.' },
  orders: { src: '/shots/orders.webp', w: 1440, h: 900, alt: 'The Orders list with status filters, order codes, customers, totals and fulfilment status.' },
  inventory: { src: '/shots/inventory.webp', w: 1440, h: 900, alt: 'The Inventory page: stock levels, reorder alerts and prices for each product.' },
  analytics: { src: '/shots/analytics.webp', w: 1440, h: 900, alt: 'The Analytics page: sales over time, best sellers and demand, each with a chart and a table view.' },
} as const

/** The five jobs the product does, in the order the page shows them. Each sentence is something the code does today (see docs/FEATURES in the repository). */
export const SHOWCASE = {
  voice: {
    title: 'Multilingual voice ordering',
    body: 'Customers say the order the way they talk: Gujarati, Hindi, English, Hinglish or one of seven more Indian languages, mixed mid-sentence if they like. In the browser the voice is recorded and sent through your server to Gnani Prisma, and the order desk shows what it heard before anything is added to the bill.',
  },
  recognition: {
    title: 'Intelligent product recognition',
    body: 'The same item is named in many ways, in many scripts and spellings. SWARA AI reads quantities like “dhai kilo” or “ek dozen” as numbers, matches names across scripts, and when two products fit it asks which one instead of guessing.',
  },
  inventory: {
    title: 'Smart inventory management',
    body: 'Stock is checked before anything is promised to a customer, and every sale lowers the shelf count.',
    points: [
      'Out-of-stock items are named when a customer asks for them.',
      'Low and finished items are listed before a customer asks for them.',
      'Every manual change to the count is recorded as a stock movement.',
    ],
  },
  orders: {
    title: 'Automated order processing',
    body: 'The bill is editable and adds up at every step. It is read back in the customer’s language, and the order is saved, with stock reduced, only after the customer says yes. Saved orders can be found by code, customer or status.',
  },
  analytics: {
    title: 'Business analytics and insights',
    body: 'Every figure is worked out from recorded orders, never typed in by hand, and every chart has a table view.',
    notes: [
      { title: 'Sales over time', body: 'Daily, weekly and monthly sales, with the change from the period before.' },
      { title: 'What sells', body: 'Best sellers, and which products are rising or falling in demand.' },
      { title: 'What runs out', body: 'The restock list, stock value, and items likely to run out within days.' },
    ],
  },
} as const

/** Sentences shown in the voice-ordering picture. They are the same sentences as the example buttons of the live demo, which the language engine reads
 *  into the item and quantity marked here (checked against the running parser). `mark` = the words it picks out. */
export const SPECIMEN: { language: string; lang: string; parts: { t: string; mark?: boolean }[] }[] = [
  { language: 'Gujarati', lang: 'gu', parts: [{ t: 'મને ' }, { t: 'બે કિલો ખાંડ', mark: true }, { t: ' અને ' }, { t: 'એક લિટર દૂધ', mark: true }, { t: ' જોઈએ છે' }] },
  { language: 'Hindi', lang: 'hi', parts: [{ t: 'भैया ' }, { t: 'ढाई किलो चीनी', mark: true }, { t: ' और ' }, { t: 'आधा किलो चायपत्ती', mark: true }, { t: ' दे दो' }] },
  { language: 'Hinglish', lang: 'en', parts: [{ t: 'Bhai mujhe ' }, { t: '2 kilo chawal', mark: true }, { t: ' aur ' }, { t: '1 litre doodh', mark: true }, { t: ' chahiye' }] },
]

/** Four ways to name one item. Each of these resolves to Milk in the running app (checked with the parser). */
export const VARIANTS: { text: string; lang: string; how: string }[] = [
  { text: 'doodh', lang: 'en', how: 'Roman letters' },
  { text: 'દૂધ', lang: 'gu', how: 'Gujarati' },
  { text: 'दूध', lang: 'hi', how: 'Hindi' },
  { text: 'milk', lang: 'en', how: 'English' },
]

/** How the parts connect. Taken from backend/app and frontend/package.json: nothing here is planned, only what runs today. */
export const FLOW: { title: string; body: string }[] = [
  { title: 'The browser', body: 'The React app: order desk, dashboard, inventory, analytics, settings. It records voice only when you use it.' },
  { title: 'Your server', body: 'FastAPI. The language engine, the order engine, accounts and analytics all run here. The Gnani key lives here and never reaches the browser.' },
  { title: 'Your database', body: 'One SQLite file for orders, customers and stock, on your own computer or server.' },
  { title: 'Gnani speech services', body: 'Prisma turns speech into text and Timbre speaks the reply. Called from your server, with your key, and only when voice is used.' },
]

export const STACK: { part: string; what: string }[] = [
  { part: 'Interface', what: 'React 18, TypeScript in strict mode, Vite' },
  { part: 'Server', what: 'Python, FastAPI, SQLAlchemy' },
  { part: 'Data', what: 'SQLite' },
  { part: 'Speech', what: 'Gnani Prisma v2.5 for speech to text, Gnani Timbre v2.5 for text to speech' },
  { part: 'Language engine', what: 'Rule-based and deterministic, not a generative model' },
  { part: 'Typefaces', what: 'Newsreader, Geist and Noto Sans, served from the app itself (no font service)' },
]

export type TechStatus = 'working' | 'key' | 'config' | 'none'
export const STATUS_LABEL: Record<TechStatus, string> = { working: 'Working', key: 'Needs your Gnani key', config: 'Needs your settings', none: 'Not built' }

export const TECH: { area: string; what: string; status: TechStatus }[] = [
  { area: 'Language engine', what: 'A rule-based parser for Gujarati, Hindi, English and Hinglish: items, quantities, units, corrections. Deterministic, so a wrong guess cannot invent stock. Seven more languages (Marathi, Bengali, Tamil, Telugu, Kannada, Malayalam, Punjabi) were added by the same method; they are unit-tested but new, and no native speaker has reviewed them.', status: 'working' },
  { area: 'Order engine and stock', what: 'Price lookup, stock checks, an editable cart, confirm and cancel, and a record of every stock movement.', status: 'working' },
  { area: 'Analytics', what: 'Sales, best sellers, demand and stock value computed from recorded orders.', status: 'working' },
  { area: 'Accounts and security', what: 'scrypt password hashing, HttpOnly session cookies, CSRF tokens, sign-in lockout, rate limits, owner and staff roles.', status: 'working' },
  { area: 'Speech to text', what: 'Gnani Prisma v2.5, called from the server with the key the owner adds.', status: 'key' },
  { area: 'Text to speech', what: 'Gnani Timbre v2.5, for the spoken reply.', status: 'key' },
  { area: 'E-mail', what: 'Password-reset and confirmation links, and forwarding of contact messages, through the SMTP server you configure.', status: 'config' },
  { area: 'Evon', what: 'Gnani does not offer Evon through its public API, so this product does not use it.', status: 'none' },
  { area: 'Phone and WhatsApp ordering', what: 'Orders arrive through the web app only.', status: 'none' },
  { area: 'Payments and UPI', what: 'Bills are totalled; money is not collected.', status: 'none' },
  { area: 'Several shops, one account', what: 'One installation serves one shop.', status: 'none' },
  { area: 'Sign in with Google', what: 'Accounts use e-mail and password only.', status: 'none' },
]

/** What protects an account and its data. Each line below is something the code does; the sources are backend/app/auth.py, security.py, config.py and
 *  routers/settings.py. The numbers (5 tries, 15 minutes, 12 hours, 2 hours) are the defaults in config.py and can be changed by whoever installs the app. */
export const SECURITY: { icon: IconName; title: string; body: string }[] = [
  { icon: 'lock', title: 'Passwords are never kept as text', body: 'Passwords are stored as scrypt hashes. After five wrong passwords for one e-mail address, sign-in for that address pauses for 15 minutes. A wrong sign-in gets the same answer whether or not the address has an account.' },
  { icon: 'shield', title: 'Sessions you can end', body: 'The browser holds one HttpOnly cookie, which scripts on the page cannot read, and the server keeps only a hash of it. A session ends after 12 hours, or after 2 hours without use. Changing your password signs out every other device.' },
  { icon: 'check', title: 'Other websites cannot act for you', body: 'Every change made through the app carries a token that belongs to your session, and a request that a browser says came from another website is refused. Pages cannot be shown inside other sites.' },
  { icon: 'users', title: 'Owner and staff are different', body: 'The server checks the role on every request, not only on the screen. Staff can take and read orders; stock, prices, settings, customer records and exports of customer details stay with the owner.' },
  { icon: 'key', title: 'Your Gnani key stays on the server', body: 'The key is kept in the server’s settings file, never sent to the browser and never part of the source code. After it is saved, only the owner sees a masked hint of it.' },
  { icon: 'database', title: 'Your data stays with you', body: 'Orders, customers and stock live in a database on your own computer or server. There are no analytics or tracking scripts. Audio leaves your server only when you use voice, and it goes to Gnani under your key.' },
]

/** Said next to the list above so the section cannot be read as more than it is. */
export const SECURITY_LIMITS =
  'SWARA AI has not had an independent security audit or penetration test, holds no security certification, and has no two-factor sign-in. On the internet, serve it over HTTPS (the cookie then becomes Secure) and keep the server up to date.'

export const WHY: { title: string; body: string }[] = [
  { title: 'Made for how shops really talk', body: 'Customers mix languages mid-sentence and say “ek dozen” in the middle of Gujarati. SWARA AI reads that as it is said, in any script, instead of asking people to speak like a menu.' },
  { title: 'It never guesses stock or prices', body: 'Stock and prices come from your database, not from a model’s memory. A missing item is named, an unclear one is asked about, and the bill always adds up.' },
  { title: 'Honest about its data', body: 'Every product says where its name came from and whether its price is the shop’s own. Generated demo data is labelled and can be switched off everywhere.' },
  { title: 'Yours to run', body: 'It runs on your own computer or server with one command on Windows. Your orders and customers are stored in a database file you control.' },
]


export type LanguageCard = { name: string; script: string; lang: string; sample: string; note: string }

/** In use since the first release. */
export const LANGUAGES: LanguageCard[] = [
  { name: 'Gujarati', script: 'ગુજરાતી', lang: 'gu', sample: 'મને બે કિલો ખાંડ જોઈએ છે', note: 'Typed in Gujarati script or in Roman letters. Speech through Gnani Prisma.' },
  { name: 'Hindi', script: 'हिन्दी', lang: 'hi', sample: 'भैया ढाई किलो चीनी दे दो', note: 'Devanagari or Roman letters. Speech through Gnani Prisma.' },
  { name: 'English', script: 'English', lang: 'en', sample: 'one and a half kilo onion please', note: 'Including numbers in words and “dozen”. Speech through Gnani Prisma.' },
  { name: 'Hindi in Roman letters', script: 'Hinglish', lang: 'en', sample: 'bhai 2 kilo chawal aur doodh', note: 'Hindi written in Roman letters, as people type it on a phone.' },
]

/** Added in 2.3.0. Rules written for this release and unit-tested; not reviewed by native speakers and not checked against real recordings. */
export const NEW_LANGUAGES: LanguageCard[] = [
  { name: 'Marathi', script: 'मराठी', lang: 'mr', sample: 'मला दोन किलो साखर आणि एक लिटर दूध पाहिजे', note: 'Speech and replies use Gnani mr-IN.' },
  { name: 'Bengali', script: 'বাংলা', lang: 'bn', sample: 'আমার দুই কেজি চিনি আর এক লিটার দুধ লাগবে', note: 'Speech and replies use Gnani bn-IN.' },
  { name: 'Tamil', script: 'தமிழ்', lang: 'ta', sample: 'எனக்கு இரண்டு கிலோ சர்க்கரை மற்றும் ஒரு லிட்டர் பால் வேண்டும்', note: 'Speech and replies use Gnani ta-IN.' },
  { name: 'Telugu', script: 'తెలుగు', lang: 'te', sample: 'నాకు రెండు కిలోల చక్కెర మరియు ఒక లీటర్ పాలు కావాలి', note: 'Speech and replies use Gnani te-IN.' },
  { name: 'Kannada', script: 'ಕನ್ನಡ', lang: 'kn', sample: 'ನನಗೆ ಎರಡು ಕಿಲೋ ಸಕ್ಕರೆ ಮತ್ತು ಒಂದು ಲೀಟರ್ ಹಾಲು ಬೇಕು', note: 'Speech and replies use Gnani kn-IN.' },
  { name: 'Malayalam', script: 'മലയാളം', lang: 'ml', sample: 'എനിക്ക് രണ്ട് കിലോ പഞ്ചസാരയും ഒരു ലിറ്റർ പാലും വേണം', note: 'Speech and replies use Gnani ml-IN.' },
  { name: 'Punjabi', script: 'ਪੰਜਾਬੀ', lang: 'pa', sample: 'ਮੈਨੂੰ ਦੋ ਕਿਲੋ ਖੰਡ ਅਤੇ ਇੱਕ ਲੀਟਰ ਦੁੱਧ ਚਾਹੀਦਾ ਹੈ', note: 'Speech and replies use Gnani pa-IN.' },
]


export const FAQ: { q: string; a: string }[] = [
  { q: 'What is SWARA AI?', a: 'A web app for Indian Kirana stores. Customers or staff say or type an order in Gujarati, Hindi, English, one of seven more Indian languages, or a mix; SWARA AI checks the stock, adds up the bill and reads it back. It also keeps the shop’s orders, customers and sales numbers.' },
  { q: 'Which languages does it understand?', a: 'Eleven choices: Gujarati, Hindi, English and Hinglish (Hindi in Roman letters), which have been in use since the first release, and Marathi, Bengali, Tamil, Telugu, Kannada, Malayalam and Punjabi, added in version 2.3.0. The seven new ones are unit-tested but have not been reviewed by native speakers or checked against real recordings, and whether Gnani’s speech services work for each one in your account is something you confirm with the check in Settings. Other Indian languages are not supported.' },
  { q: 'Do I need a Gnani API key?', a: 'For voice, yes: speech recognition and the spoken reply are Gnani services, called with a key the owner adds in Settings. Without a key, typed orders work in exactly the same way.' },
  { q: 'Are the numbers in the screenshots real?', a: 'No. The screenshots and the pre-filled customers and orders are generated demo data, marked as such inside the app. A switch in the top bar hides demo data everywhere.' },
  { q: 'Where is my shop’s data stored?', a: 'On the computer or server where SWARA AI is installed, in a database file. The app has no analytics or tracking scripts. When you use voice, the audio and text go to Gnani under your own key.' },
  { q: 'Who can sign in?', a: 'The first account created becomes the owner (or the address set by whoever installed it). The owner can add staff, who can take orders and read the numbers but cannot change stock, prices or settings, and can turn staff accounts off.' },
  { q: 'I forgot my password. What now?', a: 'If the server is set up to send e-mail, use “Forgot password?” on the sign-in page. If it is not, the person who installed SWARA AI can reset it with a command-line tool. The sign-in page says which applies.' },
  { q: 'Does it cost anything?', a: 'SWARA AI has no billing or plans. You run it yourself. Gnani’s own terms apply to any use of their speech services with your key.' },
  { q: 'Does it work on a phone?', a: 'Yes, in the phone’s browser. The microphone only works when the page is opened over https or from the same computer (localhost).' },
]
