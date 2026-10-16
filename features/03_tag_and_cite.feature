Feature: The tag and the cite
  The tag is the card's claim (front matter "title", also the issue title). The cite is one line:
  the short cite "Last YY" (rendered bold, everything before the first comma), then the author
  quals, title, publication, date and link. Scythe drafts it from the source's front matter with
  defaultCite(); the debater can always rewrite it.

  Background:
    Given I am signed in to the team's evidence
    And a pasted source "Nuclear winter study <run>" by "Alan Robock" in "Nature Food" on "2022-08-15" with text:
      """
      Soot from burning cities would block sunlight for a decade.
      """

  @built @signed-in
  Scenario: The cite is drafted from the source
    When I open that source in the reader
    Then the cite field reads "Robock 22, Alan Robock, \"Nuclear winter study <run>\", Nature Food, 8-15-2022"

  @built @signed-in
  Scenario: Rewrite the tag
    Given a card "Soot <run>" cut from that source
    When I open the card
    And I change the tag to "Soot blocks the sun for a decade <run>"
    Then the card's front matter has "title" "Soot blocks the sun for a decade <run>"
    And the latest commit to the card reads "title: \"Soot blocks the sun for a decade <run>\" (#<n>)"

  @built @signed-in
  Scenario: Rewrite the cite with quals
    Given a card "Soot <run>" cut from that source
    When I open the card
    And I change the cite to "Robock 22, Distinguished Professor of Climate Science at Rutgers, Nature Food"
    Then the card's front matter has "cite" "Robock 22, Distinguished Professor of Climate Science at Rutgers, Nature Food"
    And the short cite "Robock 22" is shown in bold

  @partly @signed-in
  # today: clearing the tag is silently ignored and the field stays blank
  Scenario: A tag can't be emptied
    Given a card "Soot <run>" cut from that source
    When I open the card
    And I clear the tag
    Then I see "A card needs a tag."
    And the tag field reads "Soot <run>" again

  @missing @signed-in
  Scenario: Quals come from the people named in the card
    Given the card's text names "Alan Robock" and "Rutgers University"
    When I ask for quals
    Then the cite offers "Alan Robock, Rutgers University" as the quals to insert after the short cite

  @signed-in
  Scenario Outline: The short cite when the source is missing pieces
    Given a source by "<authors>" in "<publication>" on "<date>"
    When I open that source in the reader
    Then the drafted cite starts with "<short cite>"

    @built
    Examples: Scythe drafts these today
      | authors     | publication | date       | short cite     |
      | Alan Robock | Nature Food | 2022-08-15 | Robock 22      |
      |             | Nature Food | 2022-08-15 | Nature Food 22 |

    @partly
    # today: with no date the short cite is just "Robock", with nothing to say the date is missing
    Examples: A missing date is said out loud
      | authors     | publication | date       | short cite     |
      | Alan Robock | Nature Food |            | Robock No Date |
