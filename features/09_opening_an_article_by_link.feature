Feature: Opening an article by its link
  Pasting a link makes a "scythe:fetch" issue through the passthrough. The fetch.yml Action opens
  the page in headless Chromium, runs Mozilla Readability, keeps p / h2–h4 / blockquote / li / pre
  blocks, cleans the text with the same rules as sanitizeText(), and commits sources/<n>.md
  (front matter: title, url, publisher, published, authors, fetched) plus sources/<n>.html. On
  success the issue becomes "scythe:source"; on failure it is labelled "scythe:fetch-failed" with a
  comment saying why. The reader polls for sources/<n>.md every 5 seconds.

  Background:
    Given I am signed in to the team's evidence

  @built @slow @signed-in
  Scenario: A link becomes clean text you can cut from
    When I open the reader
    And I fetch the link "https://en.wikipedia.org/wiki/Nuclear_winter"
    Then within 5 minutes the reader shows the source "Nuclear winter"
    And the source's file in git has "url" "https://en.wikipedia.org/wiki/Nuclear_winter"
    And the source's text in git has no blank line inside a paragraph and exactly one between paragraphs
    And the source's issue has the label "scythe:source"

  @partly @signed-in
  # today: "Fetching on GitHub… 35s" and "A GitHub Action opens the page in headless Chromium…"
  Scenario: Waiting for the article says what's happening in plain words
    When I open the reader
    And I fetch the link "https://en.wikipedia.org/wiki/Nuclear_winter"
    Then I see "Reading the article… this takes about a minute"

  @partly @slow @signed-in
  # today: "GitHub couldn't read that page (see issue #n). Paste the text instead."
  Scenario: A paywalled page asks for the text instead
    When I open the reader
    And I fetch a link to a page with no readable article
    Then within 5 minutes the source's issue has the label "scythe:fetch-failed"
    And I see "Couldn't read this page. Paste the article's text instead."
    And the paste form is open with the link already filled in

  @missing @signed-in
  Scenario: The same link twice opens the same source
    Given the source for "https://en.wikipedia.org/wiki/Nuclear_winter" is already in the team's evidence
    When I fetch the link "https://en.wikipedia.org/wiki/Nuclear_winter"
    Then the reader opens that source at once
    And no new source is made

  @missing @signed-in
  Scenario: The cite is drafted from the fetched page
    When the article has been fetched
    Then the cite field starts with the first author's last name and the two-digit year
