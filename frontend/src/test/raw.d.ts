/* Lets a test read a repository file as text with `import x from '../path/file.json?raw'` (Vite feature). */
declare module '*?raw' {
  const content: string
  export default content
}
