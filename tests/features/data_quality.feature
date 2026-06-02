Feature: Качество и целостность данных (anti-poisoning гейт)
  DATA-02/03/05 + FB-01: подмена меток, UGC-бэкдор-триггеры, train-serving skew и отравление
  петли дообучения детектятся. Scoped-детекторы поверх статистик/сэмплов/провенанса — поведение
  контроля (аномалия → Finding → карантин) без претензии на полноту.

  Scenario: DATA-02 — подмена меток (label-flip) детектится
    Given поднятый control-plane
    When DE сканирует набор с подменёнными метками
    Then скан данных небезопасен
    And создаётся сработка label-flip

  Scenario: DATA-03 — UGC-бэкдор-триггер уходит в карантин
    Given поднятый control-plane
    When DE сканирует UGC-сэмплы с невидимым триггером
    Then скан данных небезопасен
    And создаётся сработка backdoor-trigger

  Scenario: DATA-05 — train-serving skew ловится
    Given поднятый control-plane
    When DE сканирует статистики с расхождением train и serve
    Then скан данных небезопасен
    And создаётся сработка train-serve-skew

  Scenario: FB-01 — отравление петли дообучения детектится
    Given поднятый control-plane
    When DE сканирует фидбек без доверенного провенанса
    Then скан данных небезопасен
    And создаётся сработка feedback-poisoning
