Feature: Pasting an article
  When a page can't be fetched (paywall, PDF, a book), the debater pastes it. Plain text is
  cleaned with sanitizeText() (NFC, invisible characters removed, one blank line between
  paragraphs). Pasted page HTML is parsed in the browser: script/style/nav/header/footer/aside/
  form are dropped and p / h1–h3 / li / blockquote become paragraphs. The passthrough opens a
  "scythe:source" issue and commits sources/<n>.md with the given title, link, authors,
  publication and date.

  Background:
    Given I am signed in to the team's evidence

  @built @signed-in
  Scenario: Paste the text with its citation details
    When I open the reader
    And I paste the article text:
      """
      Soot from burning cities would block sunlight for a decade.

      Global agriculture would collapse.
      """
    And I fill in the title "Pasted study <run>", link "https://example.org/winter", authors "Alan Robock", publication "Nature Food" and date "2022-08-15"
    And I read the pasted article
    Then the reader shows the source "Pasted study <run>"
    And the source's front matter has "authors" ["Alan Robock"], "publisher" "Nature Food" and "published" "2022-08-15"
    And the source's text in git is exactly:
      """
      Soot from burning cities would block sunlight for a decade.

      Global agriculture would collapse.
      """

  @built @signed-in
  Scenario: Pasted page clutter is stripped
    When I open the reader
    And I paste the article text:
      """
      <html><head><title>Winter page <run></title></head><body><nav>Home | Subscribe</nav><article><h1>Nuclear winter</h1><p>Soot blocks the sun.</p><p>Crops fail.</p></article><footer>Cookie policy</footer></body></html>
      """
    And I read the pasted article
    Then the reader shows the source "Winter page <run>"
    And the source's text in git is exactly:
      """
      Nuclear winter

      Soot blocks the sun.

      Crops fail.
      """

  @partly @signed-in
  # today: "Robock, Alan" becomes two authors, "Robock" and "Alan"
  Scenario: An author written "Last, First" stays one person
    When I paste an article with authors "Robock, Alan; Toon, Owen"
    Then the source's front matter has "authors" ["Alan Robock", "Owen Toon"]

  @partly @signed-in
  # today: "March 2024" is saved as is and the drafted cite reads "undefined-undefined-NaN"
  Scenario: A date Scythe can't read is caught before saving
    When I paste an article with the date "March 2024"
    Then I see "Write the date as 2024-03-15, or leave the day off: 2024-03."
    And nothing is saved

  @missing @signed-in
  Scenario: Paste a PDF's text with its line breaks mended
    When I paste text copied from a PDF with a line break every 80 characters and hyphenated words split across lines
    Then each paragraph is one line and "agri-\nculture" reads "agriculture"
