FROM golang:1.25-alpine AS build
WORKDIR /src
ENV GOPROXY=https://proxy.golang.org,direct \
    GOTOOLCHAIN=local
COPY go/ .
ARG BIN=server
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/app ./cmd/${BIN}

FROM alpine:3.20
WORKDIR /app
RUN apk add --no-cache ca-certificates tzdata wget
COPY --from=build /out/app /app/app
EXPOSE 8000
ENTRYPOINT ["/app/app"]
