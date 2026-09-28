# Wind, cold, and your 2014 thesis

*Literature check and thesis feedback · September 2026*

What has been published on weather and NFL offense before and since your CMC senior thesis, which of your findings have held up, and what a careful referee would flag in the paper itself.

Published page: https://claude.ai/artifact/ULdbHSkgLLcf6bzBGEppNU

| | |
|---|---|
| **Senior thesis** | Claremont McKenna College · Spring 2014 · Reader: Prof. Darren Filson |
| **Sample** | Seasons 2002–2013 · 3,133 regular and postseason games · 6,266 team-games |
| **Weather** | Kickoff temp + wind from NFL Game Books via Pro-Football-Reference · wind chill used as temperature |
| **Model** | OLS, team and season fixed effects, robust SEs |
| **Thesis** | https://scholarship.claremont.edu/cmc_theses/830/ |

---

## Short answer

**Nobody has redone your analysis.** The nearest academic work is a 2026 paper in *Temperature* that tests your acclimation idea on wins and point margin, and a 2017 *International Journal of Sport Finance* paper on weather and betting totals. The rest is class projects, a high-school summer-program paper, and fantasy and betting analysis.

**Your main results have held up.** Later work keeps finding what you found. Wind is the most consistent drag on passing, cold matters less, and wind pushes teams toward the run. The warm-team-in-the-cold effect now has peer-reviewed support.

**Cited once, but easy to find.** Google Scholar lists one citing work, a 2019 master's thesis on soccer. Your thesis was also the first search result for several of my queries on this topic.

**The weak spots are fixable.** The acclimation model can't tell "cold" apart from "colder than home." Games with zero interceptions, fumbles or sacks dropped out of those regressions. Playoffs aren't controlled for. Several numbers in the text misread log and interaction coefficients.

---

## The four closest matches

These ask nearly your question. Two are peer-reviewed; two are student work.

### 2026 · [Game-day temperatures are predictive of National Football League game outcomes when teams from different climates compete against each other](https://www.tandfonline.com/doi/abs/10.1080/23328940.2025.2588731)
Roberts, Urwin, Regan, Bowe & Warmington · *Temperature* 13(1): 51–58 · [PubMed](https://pubmed.ncbi.nlm.nih.gov/41797813/) · Peer-reviewed · Closest to Analysis 3

- **Data:** Official NFL Game Book temperatures, 2017–2025. Games between teams based north of 39°N (17 teams) and south of it (15 teams). Mixed-effects models.
- **Found:** The northern team's odds of winning fell as game-day temperature rose (odds ratio 0.974 per °C), and its point margin dropped 0.175 points per °C. The effect came mainly from games played in the south.
- **Vs. yours:** The same acclimation idea as your third analysis, tested on wins and margin instead of passing and rushing. They split teams by latitude. You compared each visitor's weekly home temperature with game conditions, which is finer-grained. Their seasons (2017–2025) don't overlap with yours (2002–2013).

### 2017 · [The Impact of Atmospheric Conditions on Actual and Expected Scoring in the NFL](https://journals.sagepub.com/doi/full/10.1177/155862351701200102)
Rodney J. Paul · *International Journal of Sport Finance* 12(1) · Peer-reviewed

- **Found:** Humidity helps explain the gap between actual scoring and the betting total. Simple betting rules built on humidity and wind rejected market efficiency. Humidity appeared to help the running game.
- **Vs. yours:** Game-level scoring and market efficiency rather than team passing and rushing. It adds humidity and air density, which you didn't have.

### 2016 · [Weather and the NFL](https://web.stanford.edu/class/stats50/projects16/Houghton-BerryParkPierce-paper.pdf)
Houghton-Berry, Park & Pierce · Stanford STATS 50 · Class project

- **Data:** NFLweather.com, 2009–2015, with rain, snow, indoor and turf indicators. OLS and lasso regressions.
- **Found:** Each mph of wind cost about 0.26 points per game. Rain added 3.7 points to the home team's margin, and colder games favored the home team.
- **Vs. yours:** Similar game-level regressions, and it has the precipitation you lacked. It has no control for home-field advantage, which the authors acknowledge. It cites Burke's 2012 posts, not your thesis.

### 2022 · [Whether Weather, Wind Speed and Temperature, Impacts Offensive Success in the NFL](https://wsb.wharton.upenn.edu/wp-content/uploads/2022/09/2022_Football_Parks_Weather.pdf)
Parks, Ceklosky, Roseman, Awad & Yan · Wharton Moneyball Academy, a summer program for high-school students

- **Data:** nflfastR play-by-play, with EPA per play averaged by wind and temperature band.
- **Found:** Passing EPA per play fell from +0.037 in 1–6 mph wind to −0.048 in 26–34 mph wind, while rushing EPA stayed roughly flat. Passing EPA rose with temperature; rushing EPA was best in the cold.
- **Vs. yours:** Your question with the modern efficiency metric, but only band averages. There are no controls for team quality, home field or roof.

---

## Literature map

Everything relevant I found, grouped by when it appeared relative to your thesis. I read each item except the one marked at the end.

**Who cites you:** Google Scholar lists one citing work: [Palinggi (2019)](https://scholar.google.com/scholar?cites=17265200358591335717), *Predicting soccer outcome with machine learning based on weather condition*, a master's thesis at Universitat Jaume I.

### Before your thesis (8 items)

- **2007 · [The Home Team Weather Advantage and Biases in the NFL Betting Market](https://www.sciencedirect.com/science/article/abs/pii/S0148619506001019)**. Borghesi · *Journal of Economics and Business* 59(4) · *You cited.* Gave an acclimation advantage to the team whose five-day home temperatures were closer to game-day conditions. Teams with the advantage outperformed, and the betting market didn't fully price it. Your third analysis builds on this.
- **2008 · [Weather Biases in the NFL Totals Market](https://www.tandfonline.com/doi/full/10.1080/09603100701335432)**. Borghesi · *Applied Financial Economics* 18(12) · [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2149710) · *Not cited.* In 1984–2004 games, heat, wind and rain lowered scoring, and the totals market didn't fully price it. A weather-based under strategy won out of sample. It's by the same author as your key source and measures the wind and rain effects directly.
- **2012 · [Weather Effects on Passing](http://www.advancedfootballanalytics.com/2012/01/weather-effects-on-passing.html)**. Brian Burke · Advanced NFL Stats · *You cited.* Cold lowered adjusted yards per attempt for every type of team. Wind mattered mostly above 15 mph and hurt dome teams no more than anyone else. In 20+ mph wind, offenses traded only about five passes for runs.
- **2012 · [How Does Temperature Affect Road Teams? (And Dome Teams in Particular?)](http://www.advancedfootballanalytics.com/2012/01/how-does-temperature-affect-road-teams.html)**. Brian Burke · Advanced NFL Stats · *Discussed, not in references.* Dome teams went 0–8 on the road at 20°F or colder and 3–23 at 30°F or colder, about 20% once playoffs are removed. Cold-climate visitors showed no decline.
- **2013 · [Going for Three: Predicting the Likelihood of Field Goal Success with Logistic Regression](https://www.sloansportsconference.com/research-papers/going-for-three)**. Clark, Johnson & Stimpson · MIT Sloan Sports Analytics Conference · *Not cited.* A play-level model of 2000–2011 kicks. Cold, wind and precipitation lowered success, while altitude and artificial turf raised it. It shows weather effects with controls, from the same era as your data.
- **2014 · [The Impact of Visiting Team Travel on Game Outcome and Biases in NFL Betting Markets](https://journals.sagepub.com/doi/10.1177/1527002512440580)**. Mark W. Nichols · *Journal of Sports Economics* (online 2012) · *Not cited.* Travel affects visiting teams' results (1981–2004), with mixed evidence that betting lines account for it. An acclimation study needs these controls so travel isn't mistaken for climate.
- **Jan 2014 · [Cold weather usually an issue for Manning](https://www.espn.com/blog/statsinfo/post/_/id/83631/cold-weather-usually-an-issue-for-manning)**. ESPN Stats & Information · Media. Manning was 8–11 in games below 40°F with 30 touchdowns and 23 interceptions, against 85–35 otherwise. Your acknowledgments credit this storyline.
- **2014 · [Association of Domed Stadium to Winning NFL Games](https://ww2.amstat.org/meetings/proceedings/2014/data/assets/pdf/313577_91385.pdf)**. Teramoto & Cross · JSM Proceedings, Statistics in Sports · *Same year as yours.* For 2009–2013, after adjusting for team quality and schedule, dome teams won fewer road games (38.7% vs 43.2%) and had no significant home edge. It also opens with the Manning cold-weather story.

### Academic work since (5 items)

- **2014 · [An expectation-based metric for NFL field goal kickers](https://www.degruyterbrill.com/document/doi/10.1515/jqas-2013-0039/html)**. Pasteur & Cunningham-Rhoads · *Journal of Quantitative Analysis in Sports* 10(1) · Peer-reviewed. A logistic model of kick success with temperature, wind and a Denver altitude flag, used to rate kickers against expectation. Your conclusion proposed kicking as the next step; this paper and Clark et al. (2013) cover it.
- **2016 · [A relationship between temperature and aggression in NFL football penalties](https://pmc.ncbi.nlm.nih.gov/articles/PMC6188739/)**. Craig, Overbeek, Condon & Rinaldo · *Journal of Sport and Health Science* 5(2) · Peer-reviewed. Across 2,326 games, hotter weather predicted more aggressive penalties for home teams but not visitors. Your Table 9 found fewer visitor penalties in colder-than-home games and attributed it to fewer plays. Heat and aggression is a second explanation.
- **2017 · [The Impact of Atmospheric Conditions on Actual and Expected Scoring in the NFL](https://journals.sagepub.com/doi/full/10.1177/155862351701200102)**. Rodney J. Paul · *International Journal of Sport Finance* · Peer-reviewed. Humidity and wind in the betting totals market. See the closest matches above.
- **2025 · [Associations Between Match-Play Characteristics and Environmental Temperatures in 4 Professional Football Leagues](https://pmc.ncbi.nlm.nih.gov/articles/PMC11829705/)**. Schwarz, Duffield, Novak, Compton & Meyer · *European Journal of Sport Science* 25(3) · Soccer. In 1,585 soccer matches, hotter games had fewer short passes and touches, meaning slower and more static play. The same question is now studied in other sports with event-level data.
- **2026 · [Game-day temperatures are predictive of NFL game outcomes when teams from different climates compete](https://www.tandfonline.com/doi/abs/10.1080/23328940.2025.2588731)**. Roberts et al. · *Temperature* 13(1) · Peer-reviewed. Acclimation tested on wins and margin, 2017–2025. See the closest matches above.

### Public analysis since (7 items)

- **2016 · [Effect of Cold Weather on NFL Games](https://blog.hawkblogger.com/2016/01/effect-of-cold-weather-on-nfl-games.html)**. Hawk Blogger · Blog analysis. Combined turnovers rose 42% below 20°F, and yardage fell about 10%. Home teams were 28–11 in games below 10°F going back to 1960.
- **2016 · [Weather and the NFL](https://web.stanford.edu/class/stats50/projects16/Houghton-BerryParkPierce-paper.pdf)**. Stanford STATS 50 · Class project. Wind, rain and home margin, 2009–2015. See the closest matches above.
- **2018 · [Weather Effects and Fantasy Football (three parts)](https://www.4for4.com/2018/weather-effects-and-fantasy-football-part-3)**. Chris Allen · 4for4 · Fantasy analysis. Rain had little effect, and snow shifted production toward running backs and tight ends. Part 3 found no link between a QB's combine throwing velocity and how well his deep passing held up in wind.
- **2020 · [Analyzing the Effect of Weather in the NFL](https://www.thespax.com/nfl/analyzing-the-effect-of-weather-in-the-nfl/)**. Ahmed Cheema · The Spax · Blog analysis. Completion rate fell from 60.3% in wind under 10 mph to 54.7% at 20 mph and up. Adjusted net yards per attempt fell from 5.79 to 4.62, and field-goal rate from 83.8% to 76.9%.
- **2022 · [Whether Weather, Wind Speed and Temperature, Impacts Offensive Success in the NFL](https://wsb.wharton.upenn.edu/wp-content/uploads/2022/09/2022_Football_Parks_Weather.pdf)**. Wharton Moneyball Academy · High-school program. EPA per play by wind and temperature band. See the closest matches above.
- **2024 · [Does Wind Matter in Fantasy Football?](https://www.fantasylife.com/articles/best-ball/does-wind-matter-in-fantasy-football)**. Chris Allen · Fantasy Life · Fantasy analysis. In 1,311 games from 2018–2022, completion percentage over expected fell 1.6 points in wind and pass rate over expected fell 2.8 points. Only 48 games (3.7%) topped 20 mph. Nearly half of the biggest accuracy swings came with a crosswind.
- **2026 · [Weather & NFL Scoring: It's the Wind](https://nflanalytic.com/explainer-weather-and-scoring.html)**. C. B. Zakarian · NFL Analytics · Data explainer. Across 7,276 games from 1999–2025, combined scoring falls from 44.7 points in 0–5 mph wind to 40.5 at 16+ mph. Across temperature bands it stays between 43.0 and 43.7. Dome games average 46.9.

### Found but couldn't open (1 item)

- **n.d. · ["Football Weather": Diving Into the Effects of Weather on NFL QB Performance](https://medium.com/data-science/football-weather-diving-into-the-effects-of-weather-on-nfl-qb-performance-f0edb420623d)**. Josh Mancuso · Towards Data Science on Medium · *Not reviewed.* The title matches your topic closely, but the page blocked automated reading, so I can't summarize it.

---

## What held up

Your findings next to later evidence. Effects are per 10 mph of wind or 10°F of temperature, converted from your log coefficients.

| Finding | Your estimate | Later evidence | Status |
|---|---|---|---|
| Wind hurts passing | Pass yards −6.8%, about 15 yards per team. Completion rate −1.4 points. (Table 5) | Cheema 2020: completion 60.3% → 54.7% from under 10 to 20+ mph. Allen 2024: CPOE −1.6 points. Zakarian 2026: about 4 fewer combined points from calm to 16+ mph. | Held up |
| Cold hurts passing a little | 10°F colder: pass yards −1.7%, completion rate about −0.5 points. (Table 5) | Burke 2012 and Wharton 2022: passing efficiency drops in the cold. Zakarian 2026: scoring barely changes with temperature. | Held up |
| Wind pushes teams toward the run | Rush share up about 1.2 points of plays overall and 2.0 for visitors. (Tables 5, 7) | Allen 2024: pass rate over expected −2.8 points in wind. Burke 2012: about five passes become runs at 20+ mph. | Held up |
| Warm-climate visitors do worst in freezing games | Largest pass-yard loss per degree of home-to-game drop: 3.6% per 10°F for Warm visitors. (Table 8) | Roberts et al. 2026: familiar temperatures predict wins and margin. Burke 2012: dome visitors 0–8 at 20°F or colder. | Replicated on outcomes |
| Teams from windy stadiums cope better (H3) | No. Windy-stadium visitors lost the most pass yards per mph. (Table 8) | Burke 2012: wind hurt dome teams no more than other teams. | Your "no" held up |
| Visitors are more weather-sensitive than home teams | Pooled Home × weather terms not significant (Table 5). Wind costs home QBs more passer rating than visitors (Table 6). | Stanford 2016 and Hawk Blogger 2016: the home edge grows in rain and extreme cold, measured on scores. | Unsettled |

The warm-team result is now supported for wins and margin. Nobody has yet tested whether it runs through passing efficiency, which was your angle.

---

## Hypothesis scorecard

The thesis states six hypotheses on pp. 12–13 but never says which ones held. Here is what your own tables show.

| Hypothesis | What your tables show | Verdict |
|---|---|---|
| **H1** · Visitors' passing is more vulnerable to freezing conditions than home teams' | Table 6: the Freezing dummy cut home teams' completion rate (−3.3%, p < .05) but not visitors' (−1.0%, n.s.). Table 5's Home × Freezing terms are all insignificant. | Not supported |
| **H1A** · Visitors are likelier to swap passes for runs in extreme weather | Table 7: visitors shift toward the run in wind (+4.4% rush share per 10 mph, p < .01) and home teams don't. In the cold it's the reverse. Table 5's pooled test of the difference is insignificant. | Mixed |
| **H2** · Big drops from home temperature hurt visitors' passing | Table 8: in freezing games, pass yards fall 3.6% per 10°F of drop for Warm visitors and 2.4% for Mid visitors (both significant). | Consistent, see #1 |
| **H2A** · Those drops push visitors toward the run | Table 9: no temperature-differential term is significant for rush share or rush attempts. The thesis notes this on p. 29. | Not supported |
| **H3** · Wind hurts visitors from calm stadiums more than visitors from windy ones | Table 8: per 10 mph, pass yards fall 6.3% (dome), 8.3% (light wind), 13.4% (heavy wind). The order is reversed. | Reversed |
| **H3A** · Wind pushes teams toward the run, more for teams from calm stadiums | Table 9: rush share rises with wind in all three groups (all significant), most for heavy-wind teams (+6.1% vs +4.0–4.6%). | Half supported |

---

## Feedback

As a 2014 undergraduate thesis, this is strong work. The items below are what a journal referee would raise today, ordered by how much each could change the conclusions. Page and table numbers refer to your PDF.

### What's strong

- You built an original game-level dataset with your own scraper, years before nflfastR made this easy.
- You ran fixed-effects regressions against stated hypotheses when most public work was band averages.
- Your acclimation measure, each visitor's weekly home temperature against game conditions by climate group, is more detailed than the latitude split in the 2026 journal paper.
- Your headline results agree with a decade of later data.

### Could change conclusions: identification and inference (6 items)

**#1 · The acclimation model can't separate "cold" from "colder than home"**

Table 8 has no term for game temperature itself. The differential interactions also enter without their own dummies (Warm × Freezing and so on), so each slope is forced through zero at a 0°F differential. No Warm visitor in a freezing game is anywhere near zero: all 53 have differentials between −40 and −81°F. For those games, a bigger drop from home and a colder game are nearly the same variable.

The Mid-visitor slope on pass yards (2.4% per 10°F) almost matches the plain temperature slope for all visitors in Table 6 (2.2%). Most of it may be the ordinary cold effect. Only the Warm slope (3.6%) stands out, and the gap is never tested.

*Fix:* Include game temperature, interact it with the visitor's home climate, and keep the main effects. Then test whether warm-climate visitors lose more than cold-climate visitors at the same game temperature.

**#2 · Games with zero events dropped out of the log regressions**

The log of zero is undefined, so games with no interceptions, fumbles, turnovers or sacks fell out of those columns. The sample sizes in Tables 8 and 9 show it.

```
INT / attempt   N = 1,960 of 3,111   37% dropped
Fumbles         N = 2,348 of 3,111   25% dropped
Turnovers       N = 2,498 of 3,111   20% dropped
Sacks           N = 2,698 of 3,111   13% dropped
```

Those columns describe only games where the event happened at least once, which is a different question.

*Fix:* Use Poisson or negative binomial models for counts, with pass attempts or dropbacks as the exposure, or model rates in levels.

**#3 · Playoffs are in the sample with no control**

Your literature review (p. 10) faults Burke for playoff selection bias: cold games cluster in January, when better teams host. The thesis includes postseason games without a playoff indicator, so the same bias can load onto the temperature and freezing coefficients. Late-season fatigue and injuries raise the same problem.

*Fix:* Add a playoff dummy and week-of-season effects, and report results with playoffs dropped.

**#4 · Team fixed effects don't track roster changes**

The Data section (p. 15) says team and season fixed effects account for players joining or leaving. Separate team and season effects give each franchise one average across all 12 years, so the 0–16 Lions of 2008 and the playoff Lions of 2011 count as the same team.

*Fix:* Use team-by-season fixed effects for offense and defense, or control for the pre-game point spread.

**#5 · Standard errors treat linked rows as independent**

Weather is identical for both teams in a game, and Table 5 stacks both teams (6,266 rows from 3,133 games). Heteroskedasticity-robust errors assume those rows are independent, which makes the weather coefficients look more precise than they are. The many results reported at the 10% level make this matter more.

*Fix:* Cluster by game at minimum. Clustering by stadium-season is safer, since weather is correlated within a stadium across a season.

**#6 · The abstract and conclusion claim more than the tables show**

On "visiting teams are more sensitive to extreme weather": Table 5 tests exactly that, and none of its Home × Wind or Home × Temperature passing terms is significant (you note this on p. 23). In Table 6, wind costs home teams more passer rating than visitors (−0.46 vs −0.22 per mph).

The "roughly twice as much" line on temperature (p. 26) compares 2.22% with 1.62%, a ratio of 1.4. The claim that cold-climate teams "improve" in freezing games (p. 30) rests on insignificant coefficients. The abstract's cold-to-run shift holds only for home teams (Table 7).

*Fix:* Test home-versus-away differences inside one pooled model, report the p-values, and keep only what passes in the abstract.

### Misread numbers: interpreting the coefficients (4 items)

**#7 · The home-advantage figures describe a 0°F game**

Because Home is interacted with uncentered temperature and wind, the Home coefficient is the home edge at a 0°F wind chill with no wind. At the sample means (57°F, 7.4 mph) the rushing-yards edge is about 10%, not 25.5%, and the passer-rating edge is about 4.2 points, not 6.8. The line on p. 23 that 80°F weather eliminates the rushing edge doesn't reproduce either.

```
Rush yards, mean weather   0.255 − 0.00229×57 − 0.00391×7.4          = 0.096 → +10%
Rush yards, 80°F, calm     0.255 − 0.00229×80 + 0.0614 (Home×Hot)    = 0.133 → +14%
Passer rating, mean        6.795 − 0.0225×57 − 0.182×7.4             = +4.2 points
```

*Fix:* Center temperature and wind before interacting them, for example at 60°F and 0 mph, so the Home term means something on its own.

**#8 · Relative changes read as percentage points**

With logged rates, "completion percentage falls 2.4%" means 2.4% of the rate: about 60.3% to 58.9%, or 1.4 points. On p. 25, a 4.4% rise in visitors' log rush share becomes "substitute a rush attempt for a pass attempt in 4% of all offensive attempts." The actual shift is about 2 points of play share (44.6% to 46.6%), roughly one play per game.

*Fix:* Report effects in football units: yards, percentage points, plays per game.

**#9 · "29% of the variation" is a predicted drop at the edge of the data**

On p. 29, the 81°F differential is said to "account for over 29% in the variation in pass yards." The coefficient implies a predicted fall in pass yards: 0.00361 × 81 = 0.29 log points, or 25% in exact terms. It's a point prediction for the most extreme game in a 53-game cell. It isn't a share of variance.

**#10 · Confidence language, and one flipped sign**

"The regression estimates with 99% confidence that wind has an effect" (p. 25) should read "significant at the 1% level." A p-value isn't the probability that an effect is real. The same fix applies to "estimates with 95% confidence" on p. 24.

That p. 24 sentence also has the sign backwards. It says home teams lose 2.3% of rush yards with every 10°F drop. Table 5's Home × Temperature coefficient (−0.00229) means they gain about 2.3%, which matches your p. 26 discussion and the conclusion.

### Data and measurement: what went into the model (7 items)

**#11 · Wind chill as the temperature variable**

Wind chill folds wind into temperature while wind is also in the model, so the temperature coefficient never holds wind fixed. The NWS formula is also defined only at or below 50°F with wind above 3 mph, and the thesis doesn't say it was limited to that range. Outside it, the formula runs hot.

```
80°F, 10 mph wind   → formula gives 83.2°F
72°F dome, 0 mph    → formula gives 80.5°F   (would trip the Hot ≥ 80 dummy)
```

Check the scraper code. If the formula ran on every game, the Hot coefficients partly measure something else.

*Fix:* Use air temperature and wind as separate variables, keep wind chill as a robustness check, and use heat index for hot games. Pro-Football-Reference lists humidity.

**#12 · Precipitation was obtainable**

The thesis says precipitation wasn't available (p. 16). Borghesi (2008) used rain data for games back to 1984, and hourly NOAA station records cover every NFL city. Rain and high wind often arrive together in storms, so leaving rain out probably inflates the wind coefficients somewhat.

**#13 · Roofs and filled-in weather**

Dome games without weather data were set to 72°F and calm. Retractable roofs are open for some games and closed for others, and Pro-Football-Reference records which.

*Fix:* Control for roof status and surface (grass or turf), or drop closed-roof games from the weather regressions.

**#14 · Controls that travel with the weather**

Surface, Denver's altitude, rest days, travel distance and time zones crossed (see Nichols 2014) all correlate with weather and affect offense. None is in the model.

**#15 · The home-climate variable isn't documented**

The acclimation analysis uses "the visiting team's average temperature for the week" (p. 15) without saying where that number comes from or what dome teams get. If dome teams are set to 72°F, they all count as Warm, which puts Detroit and Minnesota in the same group as Miami and Tampa Bay. Say which it is. Burke's results suggest dome teams deserve their own group.

**#16 · Volume versus efficiency, and game script**

Pass yards fall when a team passes less, so the measure mixes strategy with skill. Yards per attempt or adjusted net yards per attempt would isolate efficiency. Rush share also rises when a team is ahead, and home teams lead more often, which likely explains much of the large home rushing edge.

*Fix:* Add per-attempt measures. For play-calling, use neutral situations (score within a touchdown, first three quarters) or pass rate over expected.

**#17 · A straight line may miss the wind threshold**

Burke and later fantasy analyses find that wind effects accelerate above about 15 mph. A linear mph term would understate strong wind and overstate light wind.

*Fix:* Use wind bins (0–5, 6–10, 11–15, 16–20, 21+ mph) or a spline, and plot the result.

### Presentation: writing, tables and sources (6 items)

**#18 · Call it passer rating**

"QBR" is the name of ESPN's Total QBR, introduced in 2011. The thesis uses the NFL passer rating, so readers may assume the wrong metric.

**#19 · Equations, captions and labels**

Model (3) is captioned as producing Tables 6 and 7; it should be 8 and 9. Model (2) is missing plus signs and coefficients on its dummies. Light and Mid wind, and High and Heavy wind, are used interchangeably across Tables 1, 3, 8 and the text. Table 4 lists "HT Yards/Completion" twice, and the second row is the visitors'.

**#20 · Add figures and one summary table**

The thesis has no figures. Binned plots of passing efficiency against wind and temperature, plus one coefficient plot comparing home and visitor effects, would make the argument faster than coefficient-by-coefficient prose. A single table of effects in yards, points and plays per game would serve most readers.

**#21 · Say which hypotheses failed**

H1, H2A and H3 were not supported, and the results section never says so. A scorecard like the one above makes rejected hypotheses part of the findings.

**#22 · Small factual slips**

Burke's zero-win dome finding covers 20°F and below, not "11–22 degree weather" (p. 10). The acknowledgments call Super Bowl XLVIII "super cold," but [kickoff was 49°F](https://en.wikipedia.org/wiki/Super_Bowl_XLVIII), so Manning's rough night came in mild weather. That makes a better opening: a cold-weather story that the data can test. The Hypotheses section also opens with a sentence fragment (p. 12).

**#23 · Literature available at the time**

Borghesi (2008), Clark, Johnson & Stimpson (2013), and Nichols (online 2012) were all published before your thesis and speak directly to it. Burke's road-team post is discussed in the text but missing from the references.

---

## If you revisit it

What a 2026 version would use. Most of this data is free.

- **Data:** [nflverse / nflfastR](https://nflfastr.com) play-by-play and schedules, 1999–2025. They include EPA, completion probability and expected pass rate, plus roof, surface, temperature, wind and closing lines. Hourly station data from [NOAA](https://www.ncei.noaa.gov/) or [Meteostat](https://meteostat.net/) adds precipitation, humidity and wind direction at kickoff and during the game.
- **Outcomes:** EPA per dropback, success rate, CPOE, air yards per attempt, and sack and interception rates. For play-calling, pass rate over expected.
- **Design:** Offense-season and defense-season fixed effects, week and playoff controls, roof and surface, errors clustered by game and stadium-season, count models for turnovers, and wind in bins.
- **Acclimation:** Game temperature × visitor home climate with main effects, plus flags for a warm team's first sub-freezing game of the season and days since its last cold game.
- **New angles:** Crosswind versus headwind from stadium orientation, which Allen's 2024 piece hints at. Next Gen Stats for time to throw and throw depth. A market test of whether closing totals still underprice wind (Borghesi 2008; Paul 2017).

**The open gap.** I found no peer-reviewed study that estimates weather effects on NFL passing efficiency at the play level with team-quality controls and an acclimation design. Your thesis was aimed at that question in 2014, and it's still open.

---

*Method: web and Google Scholar searches, OpenAlex and Europe PMC lookups, and a direct read of each source except where marked. Thesis numbers come from Tables 3–9 of the Scholarship@Claremont PDF. Log-point effects are converted with e^β − 1 where the exact figure matters. Compiled September 27, 2026.*
