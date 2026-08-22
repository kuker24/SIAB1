package audit

import "log"

func Record(event string, detail string) {
	if event == "" {
		return
	}
	if detail == "" {
		log.Printf("audit %s", event)
		return
	}
	log.Printf("audit %s %s", event, detail)
}
