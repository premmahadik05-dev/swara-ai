import { LANGUAGES, NEW_LANGUAGES, type LanguageCard } from './content'

function Row({ l }: { l: LanguageCard }) {
  return (
    <li>
      <span className="lp-script" lang={l.lang}>{l.script}</span>
      <div className="lp-lang-body">
        <h4>{l.name}</h4>
        <p className="lp-sample" lang={l.lang}>&ldquo;{l.sample}&rdquo;</p>
      </div>
      <p className="lp-lang-note">{l.note}</p>
    </li>
  )
}

/** All eleven choices, each in its own script, in two plainly labelled groups. Says what has and has not been checked; claims nothing more. */
export function LanguageShowcase() {
  return (
    <>
      <p className="lp-status">
        <b>What has been checked.</b> The text engine&rsquo;s rules for every language are unit-tested. Gnani&rsquo;s documentation lists each language for speech recognition and for voice, but
        none of them has been checked against Gnani&rsquo;s live service in this release. The owner runs that check with their own key, language by language, in Settings.
      </p>
      <div className="lp-langset">
        <h3>In use since the first release</h3>
        <ul className="lp-lang-list" aria-label="Languages">{LANGUAGES.map((l) => <Row key={l.name} l={l} />)}</ul>
      </div>
      <div className="lp-langset">
        <h3 className="lp-lang-new">New in this release</h3>
        <p className="lp-lang-new-note">
          These seven were added in version 2.3.0. Their rules are unit-tested, but no native speaker has reviewed them and they have not been checked against real recordings.
          Gnani lists each as a supported language for speech and voice; whether it works well in your shop is something to test with your own key, using the check in Settings.
        </p>
        <ul className="lp-lang-list is-new" aria-label="New languages">{NEW_LANGUAGES.map((l) => <Row key={l.name} l={l} />)}</ul>
      </div>
    </>
  )
}
